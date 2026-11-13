from __future__ import annotations

import re
from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter(
    prefix="/ingestion/musicbrainz/normalization",
    tags=["ingestion", "normalization"],
)

ENTITY_NAMESPACES = {
    "artists": ("MUSICBRAINZ_ARTIST", "artist_id"),
    "release_groups": ("MUSICBRAINZ_RELEASE_GROUP", "release_group_id"),
    "releases": ("MUSICBRAINZ_RELEASE", "release_id"),
}


class ExecuteRequest(BaseModel):
    raw_record_ids: list[UUID] = Field(min_length=1, max_length=50)
    dry_run: bool = True


def entity_kind(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "unknown"
    if "primary-type" in payload or "secondary-types" in payload:
        return "release_groups"
    if "release-group" in payload or "barcode" in payload or "media" in payload:
        return "releases"
    if "name" in payload and "sort-name" in payload and "type" in payload:
        return "artists"
    return "unknown"


def _year(value: Any) -> int | None:
    if isinstance(value, str) and re.match(r"^\d{4}", value):
        return int(value[:4])
    return None


def _date_parts(value: Any) -> tuple[int | None, int | None, int | None, str, date | None]:
    if not isinstance(value, str) or not value.strip():
        return None, None, None, "YEAR", None
    value = value.strip()
    if re.fullmatch(r"\d{4}", value):
        return int(value), None, None, "YEAR", None
    if re.fullmatch(r"\d{4}-\d{2}", value):
        year, month = map(int, value.split("-"))
        if not 1 <= month <= 12:
            raise ValueError("Mese release non valido.")
        return year, month, None, "MONTH", None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        parsed = date.fromisoformat(value)
        return parsed.year, parsed.month, parsed.day, "DAY", parsed
    raise ValueError("Formato data MusicBrainz non riconosciuto.")


def _latest_decision(db: Session, raw_id: UUID):
    return db.execute(text("""
        SELECT action, entity_kind, reason, reviewer, created_at
        FROM musicbrainz_review_decisions
        WHERE raw_record_id = :raw_id
        ORDER BY created_at DESC, id DESC
        LIMIT 1
    """), {"raw_id": raw_id}).mappings().first()


def _raw_record(db: Session, raw_id: UUID, lock: bool = False):
    suffix = " FOR UPDATE OF rr" if lock else ""
    row = db.execute(text(f"""
        SELECT rr.id, rr.ingestion_run_id, rr.source_record_id, rr.payload,
               rr.payload_hash, rr.processing_status, ir.source_id
        FROM raw_records rr
        JOIN ingestion_runs ir ON ir.id = rr.ingestion_run_id
        JOIN sources s ON s.id = ir.source_id
        WHERE rr.id = :raw_id AND s.name = 'MusicBrainz'
        {suffix}
    """), {"raw_id": raw_id}).mappings().first()
    if row is None:
        raise HTTPException(404, f"Raw record {raw_id} non trovato.")
    return row


def _external_link(db: Session, kind: str, mbid: str):
    namespace, column = ENTITY_NAMESPACES[kind]
    return db.execute(text(f"""
        SELECT {column} FROM external_identifiers
        WHERE namespace = :namespace AND identifier = :mbid
    """), {"namespace": namespace, "mbid": mbid}).scalar_one_or_none()


def _readiness(db: Session, row) -> dict[str, Any]:
    kind = entity_kind(row["payload"])
    decision = _latest_decision(db, row["id"])
    result = {
        "raw_record_id": str(row["id"]),
        "mbid": row["source_record_id"],
        "entity": kind,
        "processing_status": row["processing_status"],
        "decision": decision["action"] if decision else None,
        "eligible": False,
        "blockers": [],
        "dependencies": {},
    }
    if kind not in ENTITY_NAMESPACES:
        result["blockers"].append("Tipo di entità non supportato.")
    if not decision or decision["action"] != "APPROVED":
        result["blockers"].append("È richiesta una decisione editoriale APPROVED più recente.")
    if row["processing_status"] != "PENDING":
        result["blockers"].append("Il raw_record non è nello stato PENDING.")
    try:
        UUID(str(row["source_record_id"]))
    except (ValueError, TypeError):
        result["blockers"].append("source_record_id non è un MBID valido.")
    if kind in ENTITY_NAMESPACES and row["source_record_id"]:
        existing = _external_link(db, kind, str(row["source_record_id"]))
        if existing:
            result["blockers"].append(f"MBID già collegato all'entità {existing}.")
            result["dependencies"]["existing_entity_id"] = str(existing)

    payload = row["payload"] if isinstance(row["payload"], dict) else {}
    if kind == "release_groups":
        if not str(payload.get("title") or "").strip():
            result["blockers"].append("Titolo release group mancante.")
        if not str(payload.get("primary-type") or "").strip():
            result["blockers"].append("Primary type del release group mancante.")
    elif kind == "artists":
        if not str(payload.get("name") or "").strip():
            result["blockers"].append("Nome artista mancante.")
        matches = db.execute(text("""
            SELECT id, canonical_name FROM artists
            WHERE lower(canonical_name) = lower(:name)
            ORDER BY id
        """), {"name": str(payload.get("name") or "").strip()}).mappings().all()
        if matches:
            result["dependencies"]["same_name_candidates"] = [
                {"id": str(x["id"]), "canonical_name": x["canonical_name"]} for x in matches
            ]
            result["blockers"].append("Possibile omonimia: collegamento manuale richiesto.")
    elif kind == "releases":
        if not str(payload.get("title") or "").strip():
            result["blockers"].append("Titolo release mancante.")
        group = payload.get("release-group") or {}
        group_mbid = group.get("id") if isinstance(group, dict) else None
        group_id = None
        if group_mbid:
            group_id = db.execute(text("""
                SELECT release_group_id FROM external_identifiers
                WHERE namespace='MUSICBRAINZ_RELEASE_GROUP' AND identifier=:mbid
            """), {"mbid": str(group_mbid)}).scalar_one_or_none()
        result["dependencies"]["release_group_mbid"] = group_mbid
        result["dependencies"]["release_group_id"] = str(group_id) if group_id else None
        if not group_id:
            result["blockers"].append("Release group non ancora normalizzato o collegato.")
        missing_artists = []
        credits = payload.get("artist-credit") or []
        if not isinstance(credits, list):
            credits = []
        for credit in credits:
            artist = credit.get("artist") if isinstance(credit, dict) else None
            artist_mbid = artist.get("id") if isinstance(artist, dict) else None
            if artist_mbid and not db.execute(text("""
                SELECT 1 FROM external_identifiers
                WHERE namespace='MUSICBRAINZ_ARTIST' AND identifier=:mbid
            """), {"mbid": str(artist_mbid)}).first():
                missing_artists.append(str(artist_mbid))
        result["dependencies"]["unlinked_artist_mbids"] = list(dict.fromkeys(missing_artists))
        if missing_artists:
            result["blockers"].append("Uno o più artisti dei crediti non sono collegati.")
        try:
            year, month, day, precision, parsed_date = _date_parts(payload.get("date"))
            if year is None:
                result["blockers"].append("Data release assente: lo schema richiede almeno l'anno.")
        except ValueError as exc:
            result["blockers"].append(str(exc))
        for credit in credits:
            artist = credit.get("artist") if isinstance(credit, dict) else None
            if isinstance(artist, dict) and not artist.get("id"):
                result["blockers"].append("Un credito artista non contiene un MBID.")
    result["eligible"] = not result["blockers"]
    return result


def _record_audit(db: Session, raw, kind: str, entity_id: UUID, details: dict):
    db.execute(text("""
        INSERT INTO musicbrainz_normalization_audit
            (raw_record_id, entity_kind, target_entity_id, payload_hash, details)
        VALUES (:raw_id, :kind, :target_id, :payload_hash, CAST(:details AS jsonb))
    """), {
        "raw_id": raw["id"],
        "kind": kind,
        "target_id": entity_id,
        "payload_hash": raw["payload_hash"],
        "details": json.dumps(details, ensure_ascii=False, default=str),
    })
    db.execute(text("""
        UPDATE raw_records
        SET processing_status='PROCESSED', processed_at=now()
        WHERE id=:raw_id
    """), {"raw_id": raw["id"]})


def _normalize_artist(db: Session, raw, payload: dict) -> tuple[UUID, dict]:
    name = str(payload["name"]).strip()
    span = payload.get("life-span") or {}
    country = payload.get("country")
    type_map = {
        "person": "PERSON", "group": "GROUP", "orchestra": "ORCHESTRA",
        "choir": "CHOIR", "character": "CHARACTER", "other": "OTHER",
    }
    begin_year, end_year = _year(span.get("begin")), _year(span.get("end"))
    if begin_year and end_year and end_year < begin_year:
        raise ValueError("Intervallo biografico incoerente.")
    candidates = db.execute(text("""
        SELECT id, canonical_name FROM artists
        WHERE lower(canonical_name)=lower(:name) ORDER BY id
    """), {"name": name}).mappings().all()
    if candidates:
        raise ValueError("Omonimia: selezionare un artista canonico tramite il workflow LINKED.")
    artist_id = db.execute(text("""
        INSERT INTO artists
            (canonical_name, sort_name, artist_type, country_code,
             begin_year, end_year, disambiguation)
        VALUES (:name, :sort_name, :artist_type, :country,
                :begin_year, :end_year, :disambiguation)
        RETURNING id
    """), {
        "name": name,
        "sort_name": payload.get("sort-name"),
        "artist_type": type_map.get(str(payload.get("type") or "").lower(), "OTHER"),
        "country": country.upper() if isinstance(country, str) and re.fullmatch(r"[A-Za-z]{2}", country) else None,
        "begin_year": begin_year,
        "end_year": end_year,
        "disambiguation": payload.get("disambiguation"),
    }).scalar_one()
    db.execute(text("""
        INSERT INTO external_identifiers(namespace, identifier, artist_id)
        VALUES ('MUSICBRAINZ_ARTIST', :mbid, :artist_id)
    """), {"mbid": str(raw["source_record_id"]), "artist_id": artist_id})
    alias_count = 0
    for alias in payload.get("aliases") or []:
        if not isinstance(alias, dict) or not str(alias.get("alias") or "").strip():
            continue
        db.execute(text("""
            INSERT INTO artist_aliases
                (artist_id, alias, sort_name, locale, alias_type, primary_for_locale, source_id)
            VALUES (:artist_id, :alias, :sort_name, :locale, :alias_type, :primary, :source_id)
            ON CONFLICT DO NOTHING
        """), {
            "artist_id": artist_id, "alias": str(alias["alias"]).strip(),
            "sort_name": alias.get("sort-name"), "locale": alias.get("locale"),
            "alias_type": alias.get("type"), "primary": bool(alias.get("primary")),
            "source_id": raw["source_id"],
        })
        alias_count += 1
    genre_count = 0
    for tag in payload.get("tags") or []:
        tag_name = tag.get("name") if isinstance(tag, dict) else None
        if not isinstance(tag_name, str) or not tag_name.strip():
            continue
        genre_id = db.execute(text("""
            SELECT id FROM genres WHERE lower(name)=lower(:name) ORDER BY id LIMIT 1
        """), {"name": tag_name.strip()}).scalar_one_or_none()
        if genre_id:
            db.execute(text("""
                INSERT INTO artist_genres(artist_id, genre_id)
                VALUES (:artist_id, :genre_id) ON CONFLICT DO NOTHING
            """), {"artist_id": artist_id, "genre_id": genre_id})
            genre_count += 1
    return artist_id, {"canonical_name": name, "aliases_seen": alias_count, "local_genres_linked": genre_count}


def _normalize_release_group(db: Session, raw, payload: dict) -> tuple[UUID, dict]:
    title = str(payload["title"]).strip()
    primary_type = str(payload["primary-type"]).strip()
    secondary = payload.get("secondary-types") or []
    secondary_type = ", ".join(str(x).strip() for x in secondary if str(x).strip()) or None
    year = _year(payload.get("first-release-date"))
    entity_id = db.execute(text("""
        INSERT INTO release_groups(title, primary_type, secondary_type, first_release_year)
        VALUES (:title, :primary_type, :secondary_type, :year)
        RETURNING id
    """), {"title": title, "primary_type": primary_type, "secondary_type": secondary_type, "year": year}).scalar_one()
    db.execute(text("""
        INSERT INTO external_identifiers(namespace, identifier, release_group_id)
        VALUES ('MUSICBRAINZ_RELEASE_GROUP', :mbid, :entity_id)
    """), {"mbid": str(raw["source_record_id"]), "entity_id": entity_id})
    return entity_id, {"title": title, "primary_type": primary_type, "first_release_year": year}


def _normalize_release(db: Session, raw, payload: dict) -> tuple[UUID, dict]:
    title = str(payload["title"]).strip()
    group = payload.get("release-group") or {}
    group_mbid = str(group.get("id") or "")
    group_id = db.execute(text("""
        SELECT release_group_id FROM external_identifiers
        WHERE namespace='MUSICBRAINZ_RELEASE_GROUP' AND identifier=:mbid
    """), {"mbid": group_mbid}).scalar_one()
    year, month, day, precision, release_date = _date_parts(payload.get("date"))
    media = payload.get("media") or []
    release_format = None
    if isinstance(media, list) and media and isinstance(media[0], dict):
        release_format = media[0].get("format")
    country = payload.get("country")
    country_code = country.upper() if isinstance(country, str) and re.fullmatch(r"[A-Za-z]{2}", country) else None
    label_id = None
    label_names = []
    for info in payload.get("label-info") or []:
        label = info.get("label") if isinstance(info, dict) else None
        label_name = label.get("name") if isinstance(label, dict) else None
        if isinstance(label_name, str) and label_name.strip():
            label_names.append(label_name.strip())
    if len(label_names) == 1:
        matches = db.execute(text("""
            SELECT id FROM labels WHERE lower(name)=lower(:name)
            ORDER BY id
        """), {"name": label_names[0]}).scalars().all()
        if len(matches) == 1:
            label_id = matches[0]
    release_id = db.execute(text("""
        INSERT INTO releases
            (release_group_id, title, country_code, release_date, release_year,
             release_month, release_day, date_precision, label_id, catalog_number,
             format, barcode, status)
        VALUES (:group_id, :title, :country, :release_date, :year,
                :month, :day, CAST(:precision AS date_precision), :label_id,
                :catalog_number, :format, :barcode, 'PRELIMINARY')
        RETURNING id
    """), {
        "group_id": group_id, "title": title, "country": country_code,
        "release_date": release_date, "year": year, "month": month, "day": day,
        "precision": precision, "label_id": label_id,
        "catalog_number": None, "format": release_format, "barcode": payload.get("barcode"),
    }).scalar_one()
    db.execute(text("""
        INSERT INTO external_identifiers(namespace, identifier, release_id)
        VALUES ('MUSICBRAINZ_RELEASE', :mbid, :release_id)
    """), {"mbid": str(raw["source_record_id"]), "release_id": release_id})
    artist_count = 0
    for position, credit in enumerate(payload.get("artist-credit") or []):
        if not isinstance(credit, dict) or not isinstance(credit.get("artist"), dict):
            continue
        artist = credit["artist"]
        artist_mbid = str(artist.get("id") or "")
        artist_id = db.execute(text("""
            SELECT artist_id FROM external_identifiers
            WHERE namespace='MUSICBRAINZ_ARTIST' AND identifier=:mbid
        """), {"mbid": artist_mbid}).scalar_one()
        credited_as = credit.get("name") or artist.get("name")
        db.execute(text("""
            INSERT INTO release_artists(release_id, artist_id, credited_as, credit_role, position)
            VALUES (:release_id, :artist_id, :credited_as, 'PRIMARY', :position)
            ON CONFLICT DO NOTHING
        """), {
            "release_id": release_id, "artist_id": artist_id,
            "credited_as": credited_as, "position": position,
        })
        artist_count += 1
    return release_id, {
        "title": title, "release_group_id": str(group_id), "date_precision": precision,
        "artists_linked": artist_count, "label_linked": bool(label_id),
    }


def _normalize_one(db: Session, raw, kind: str) -> dict:
    payload = raw["payload"]
    if not isinstance(payload, dict):
        raise ValueError("Il payload raw non è un oggetto JSON.")
    if kind == "artists":
        entity_id, details = _normalize_artist(db, raw, payload)
    elif kind == "release_groups":
        entity_id, details = _normalize_release_group(db, raw, payload)
    elif kind == "releases":
        entity_id, details = _normalize_release(db, raw, payload)
    else:
        raise ValueError("Tipo di entità non supportato.")
    _record_audit(db, raw, kind, entity_id, details)
    return {
        "raw_record_id": str(raw["id"]),
        "mbid": raw["source_record_id"],
        "entity": kind,
        "target_entity_id": str(entity_id),
        "outcome": "CREATED",
        "details": details,
    }


@router.get("/queue")
def normalization_queue(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    rows = db.execute(text("""
        SELECT rr.id, rr.ingestion_run_id, rr.source_record_id, rr.payload,
               rr.payload_hash, rr.processing_status, ir.source_id
        FROM raw_records rr
        JOIN ingestion_runs ir ON ir.id=rr.ingestion_run_id
        JOIN sources s ON s.id=ir.source_id
        WHERE s.name='MusicBrainz' AND rr.processing_status='PENDING'
        ORDER BY rr.received_at, rr.id
        LIMIT :limit
    """), {"limit": limit}).mappings().all()
    items = [_readiness(db, row) for row in rows]
    return {
        "items": items,
        "returned": len(items),
        "eligible": sum(1 for item in items if item["eligible"]),
        "read_only": True,
        "normalization_performed": False,
    }


@router.post("/execute")
def execute_normalization(request: ExecuteRequest, db: Session = Depends(get_db)):
    if len(set(request.raw_record_ids)) != len(request.raw_record_ids):
        raise HTTPException(422, "raw_record_ids contiene duplicati.")
    db.rollback()
    results = []
    if request.dry_run:
        for raw_id in request.raw_record_ids:
            raw = _raw_record(db, raw_id)
            results.append(_readiness(db, raw))
        return {
            "dry_run": True,
            "results": results,
            "created": 0,
            "read_only": True,
            "message": "Anteprima completata: nessuna scrittura effettuata.",
        }

    try:
        with db.begin():
            for raw_id in request.raw_record_ids:
                try:
                    with db.begin_nested():
                        raw = _raw_record(db, raw_id, lock=True)
                        readiness = _readiness(db, raw)
                        if not readiness["eligible"]:
                            results.append({
                                "raw_record_id": str(raw_id),
                                "outcome": "BLOCKED",
                                "blockers": readiness["blockers"],
                            })
                            continue
                        existing_audit = db.execute(text("""
                            SELECT id FROM musicbrainz_normalization_audit
                            WHERE raw_record_id=:raw_id
                        """), {"raw_id": raw_id}).scalar_one_or_none()
                        if existing_audit:
                            results.append({"raw_record_id": str(raw_id), "outcome": "ALREADY_NORMALIZED"})
                            continue
                        results.append(_normalize_one(db, raw, readiness["entity"]))
                except HTTPException as exc:
                    results.append({"raw_record_id": str(raw_id), "outcome": "BLOCKED", "detail": exc.detail})
                except (ValueError, IntegrityError) as exc:
                    results.append({"raw_record_id": str(raw_id), "outcome": "CONFLICT", "detail": str(exc)})
        return {
            "dry_run": False,
            "results": results,
            "created": sum(1 for item in results if item.get("outcome") == "CREATED"),
            "blocked": sum(1 for item in results if item.get("outcome") == "BLOCKED"),
            "conflicts": sum(1 for item in results if item.get("outcome") == "CONFLICT"),
            "raw_payload_modified": False,
            "message": "Elaborazione terminata. Ogni entità creata è tracciata nell'audit di normalizzazione.",
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, "Errore transazionale durante la normalizzazione.") from exc
