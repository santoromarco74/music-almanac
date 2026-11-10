from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter(prefix="/ingestion/musicbrainz/release-groups", tags=["ingestion"])
_BASE_URL = "https://musicbrainz.org/ws/2"
_RATE_LOCK = threading.Lock()
_LAST_REQUEST = 0.0


def _musicbrainz_get(path: str, params: dict) -> dict:
    """GET MusicBrainz rispettando il limite applicativo di una richiesta/sec."""
    global _LAST_REQUEST
    user_agent = os.getenv(
        "MUSICBRAINZ_USER_AGENT",
        "MusicAlmanac/1.2.0 ( https://github.com/santoromarco74/music-almanac )",
    ).strip()
    if not user_agent or user_agent.lower() in {"python-urllib", "python", "anonymous"}:
        raise HTTPException(500, "Configurare MUSICBRAINZ_USER_AGENT con applicazione, versione e contatto.")
    query = urlencode({**params, "fmt": "json"})
    with _RATE_LOCK:
        delay = 1.05 - (time.monotonic() - _LAST_REQUEST)
        if delay > 0:
            time.sleep(delay)
        request = Request(
            f"{_BASE_URL}/{path}?{query}",
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=25) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            _LAST_REQUEST = time.monotonic()
            if exc.code == 404:
                raise HTTPException(404, "Release group non trovato su MusicBrainz.") from exc
            if exc.code == 503:
                raise HTTPException(503, "MusicBrainz ha limitato la richiesta; riprovare più tardi.") from exc
            raise HTTPException(502, f"Errore HTTP MusicBrainz: {exc.code}.") from exc
        except (URLError, TimeoutError) as exc:
            _LAST_REQUEST = time.monotonic()
            raise HTTPException(502, "MusicBrainz non raggiungibile o timeout.") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            _LAST_REQUEST = time.monotonic()
            raise HTTPException(502, "Risposta JSON MusicBrainz non valida.") from exc
        _LAST_REQUEST = time.monotonic()
    if not isinstance(payload, dict):
        raise HTTPException(502, "Formato JSON MusicBrainz inatteso.")
    return payload


def _source_id(db: Session):
    source_id = db.execute(text("""
        SELECT id FROM sources
        WHERE name='MusicBrainz' AND source_type='CATALOG'
        ORDER BY created_at LIMIT 1
    """)).scalar_one_or_none()
    if source_id is not None:
        return source_id
    return db.execute(text("""
        INSERT INTO sources
          (name,source_type,base_url,publisher,reliability_tier,license_name,terms_url,notes)
        VALUES
          ('MusicBrainz','CATALOG','https://musicbrainz.org/','MetaBrainz Foundation',2,
           'CC0 database; API access terms apply','https://musicbrainz.org/doc/MusicBrainz_API',
           'Catalog source; API access subject to MusicBrainz rate limits and terms')
        RETURNING id
    """)).scalar_one()


def _persist_payload(db: Session, payload: dict, mbid: str):
    raw_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
    source_id = _source_id(db)
    run_id = db.execute(text("""
        INSERT INTO ingestion_runs(source_id,status)
        VALUES (:source_id,'RUNNING') RETURNING id
    """), {"source_id": source_id}).scalar_one()
    db.execute(text("""
        INSERT INTO raw_records
          (ingestion_run_id,source_record_id,payload,payload_hash,processing_status)
        VALUES (:run_id,:mbid,CAST(:payload AS JSONB),:digest,'PENDING')
    """), {"run_id": run_id, "mbid": mbid, "payload": raw_json, "digest": digest})
    db.execute(text("""
        UPDATE ingestion_runs
        SET finished_at=now(),status='COMPLETED',records_seen=1,
            records_imported=1,records_rejected=0
        WHERE id=:run_id
    """), {"run_id": run_id})
    return run_id


def _get_raw(db: Session, mbid: str, lock: bool = False):
    lock_clause = " FOR UPDATE OF rr" if lock else ""
    record = db.execute(text(f"""
        SELECT rr.id,rr.payload,rr.processing_status,rr.ingestion_run_id
        FROM raw_records rr
        JOIN ingestion_runs ir ON ir.id=rr.ingestion_run_id
        JOIN sources s ON s.id=ir.source_id
        WHERE rr.source_record_id=:mbid
          AND s.name='MusicBrainz' AND s.source_type='CATALOG'
        ORDER BY rr.received_at DESC,rr.id DESC
        LIMIT 1{lock_clause}
    """), {"mbid": mbid}).mappings().first()
    if record is None:
        raise HTTPException(404, "Release group non presente in raw_records; eseguire prima search o lookup.")
    return record


def _validate_mbid(mbid: str) -> None:
    try:
        UUID(mbid)
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(422, "MBID non valido.") from exc


def _candidate(payload: dict) -> dict:
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        raise HTTPException(422, "Il payload MusicBrainz non contiene un titolo valido.")
    date_text = payload.get("first-release-date") or ""
    year = int(date_text[:4]) if isinstance(date_text, str) and len(date_text) >= 4 and date_text[:4].isdigit() else None
    primary_type = payload.get("primary-type") or "OTHER"
    secondary_types = payload.get("secondary-types") or []
    return {
        "title": title.strip(),
        "primary_type": str(primary_type).strip().upper() or "OTHER",
        "secondary_type": ", ".join(str(value).strip() for value in secondary_types if str(value).strip()) or None,
        "first_release_year": year,
    }


def _artist_credits(db: Session, payload: dict) -> list[dict]:
    credits = []
    for item in payload.get("artist-credit") or []:
        if not isinstance(item, dict) or not isinstance(item.get("artist"), dict):
            continue
        artist = item["artist"]
        mbid = artist.get("id")
        artist_id = None
        if mbid:
            artist_id = db.execute(text("""
                SELECT artist_id FROM external_identifiers
                WHERE namespace='MUSICBRAINZ_ARTIST' AND identifier=:mbid
            """), {"mbid": mbid}).scalar_one_or_none()
        credits.append({
            "mbid": mbid,
            "name": artist.get("name"),
            "credited_as": item.get("name") or artist.get("name"),
            "artist_id": str(artist_id) if artist_id else None,
        })
    return credits


class NormalizeReleaseGroupRequest(BaseModel):
    existing_release_group_id: UUID | None = None


@router.post("/search")
def search_release_groups(
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = q.strip()
    if len(query) < 2:
        raise HTTPException(422, "La query deve contenere almeno due caratteri.")
    escaped = query.replace("\\", "\\\\").replace('"', '\\"')
    result = _musicbrainz_get("release-group/", {
        "query": f'releasegroup:"{escaped}"', "limit": limit,
    })
    groups = result.get("release-groups") or []
    if not isinstance(groups, list):
        raise HTTPException(502, "Risposta MusicBrainz priva di una lista release-groups valida.")
    try:
        with db.begin():
            source_id = _source_id(db)
            run_id = db.execute(text("""
                INSERT INTO ingestion_runs(source_id,status)
                VALUES (:source_id,'RUNNING') RETURNING id
            """), {"source_id": source_id}).scalar_one()
            for item in groups:
                if not isinstance(item, dict) or not item.get("id"):
                    continue
                raw_json = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                db.execute(text("""
                    INSERT INTO raw_records
                      (ingestion_run_id,source_record_id,payload,payload_hash,processing_status)
                    VALUES (:run_id,:mbid,CAST(:payload AS JSONB),:digest,'PENDING')
                """), {
                    "run_id": run_id, "mbid": item["id"], "payload": raw_json,
                    "digest": hashlib.sha256(raw_json.encode("utf-8")).hexdigest(),
                })
            db.execute(text("""
                UPDATE ingestion_runs
                SET finished_at=now(),status='COMPLETED',records_seen=:seen,
                    records_imported=:imported,records_rejected=:rejected
                WHERE id=:run_id
            """), {"seen": len(groups), "imported": sum(1 for x in groups if isinstance(x, dict) and x.get("id")),
                  "rejected": sum(1 for x in groups if not isinstance(x, dict) or not x.get("id")),
                  "run_id": run_id})
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, "Errore durante la persistenza dei risultati MusicBrainz.") from exc
    return {
        "ingestion_run_id": str(run_id), "source": "MusicBrainz", "query": query,
        "records_seen": len(groups), "processing_status": "PENDING", "results": groups,
        "message": "Risultati conservati in raw_records; nessuna entità canonica è stata creata.",
    }


@router.post("/lookup/{mbid}")
def lookup_release_group(mbid: str, db: Session = Depends(get_db)):
    _validate_mbid(mbid)
    payload = _musicbrainz_get(f"release-group/{mbid}", {"inc": "artists+releases"})
    if payload.get("id") != mbid:
        raise HTTPException(502, "MusicBrainz ha restituito un MBID differente.")
    try:
        with db.begin():
            run_id = _persist_payload(db, payload, mbid)
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, "Errore durante il salvataggio del release group.") from exc
    return {
        "ingestion_run_id": str(run_id), "mbid": mbid, "processing_status": "PENDING",
        "artist_credits": len(payload.get("artist-credit") or []),
        "releases_found": len(payload.get("releases") or []),
        "message": "Dettaglio acquisito e conservato in raw_records; non ancora normalizzato.",
    }


@router.get("/preview/{mbid}")
def preview_release_group(mbid: str, db: Session = Depends(get_db)):
    _validate_mbid(mbid)
    raw = _get_raw(db, mbid)
    candidate = _candidate(raw["payload"])
    linked = db.execute(text("""
        SELECT release_group_id FROM external_identifiers
        WHERE namespace='MUSICBRAINZ_RELEASE_GROUP' AND identifier=:mbid
    """), {"mbid": mbid}).scalar_one_or_none()
    matches = db.execute(text("""
        SELECT id,title,primary_type,first_release_year
        FROM release_groups WHERE lower(title)=lower(:title) ORDER BY id
    """), {"title": candidate["title"]}).mappings().all()
    return {
        "mbid": mbid, "raw_record_id": str(raw["id"]),
        "processing_status": raw["processing_status"], "normalized_candidate": candidate,
        "already_linked_release_group_id": str(linked) if linked else None,
        "existing_title_matches": [dict(row) for row in matches],
        "artist_credits": _artist_credits(db, raw["payload"]),
        "releases_in_payload": len(raw["payload"].get("releases") or []),
        "notes": [
            "Le singole edizioni non vengono create automaticamente.",
            "I crediti artista sono mostrati in preview e non associati al release group.",
            "Gli artisti locali sono riconosciuti soltanto tramite MBID già collegato.",
            "Il payload originale resta conservato in raw_records.",
        ],
    }


@router.post("/normalize/{mbid}")
def normalize_release_group(
    mbid: str,
    request: NormalizeReleaseGroupRequest,
    db: Session = Depends(get_db),
):
    _validate_mbid(mbid)
    db.rollback()
    try:
        with db.begin():
            raw = _get_raw(db, mbid, lock=True)
            candidate = _candidate(raw["payload"])
            linked = db.execute(text("""
                SELECT release_group_id FROM external_identifiers
                WHERE namespace='MUSICBRAINZ_RELEASE_GROUP' AND identifier=:mbid
            """), {"mbid": mbid}).scalar_one_or_none()
            if linked:
                group_id, action = linked, "ALREADY_LINKED"
            elif request.existing_release_group_id:
                group_id = request.existing_release_group_id
                exists = db.execute(text("SELECT 1 FROM release_groups WHERE id=:id"),
                                    {"id": group_id}).scalar_one_or_none()
                if not exists:
                    raise HTTPException(404, "Release group canonico indicato non esistente.")
                action = "LINKED_TO_EXISTING"
            else:
                matches = db.execute(text("""
                    SELECT id,title,primary_type FROM release_groups
                    WHERE lower(title)=lower(:title) ORDER BY id
                """), {"title": candidate["title"]}).mappings().all()
                if matches:
                    raise HTTPException(409, detail={
                        "message": "Titolo già presente: selezionare esplicitamente il record canonico.",
                        "candidate_matches": [
                            {"id": str(row["id"]), "title": row["title"], "primary_type": row["primary_type"]}
                            for row in matches
                        ],
                    })
                group_id = db.execute(text("""
                    INSERT INTO release_groups(title,primary_type,secondary_type,first_release_year)
                    VALUES (:title,:primary_type,:secondary_type,:first_release_year)
                    RETURNING id
                """), candidate).scalar_one()
                action = "CREATED"
                db.execute(text("""
                    INSERT INTO external_identifiers(namespace,identifier,release_group_id)
                    VALUES ('MUSICBRAINZ_RELEASE_GROUP',:mbid,:group_id)
                """), {"mbid": mbid, "group_id": group_id})
            db.execute(text("""
                UPDATE raw_records SET processing_status='PROCESSED',processed_at=now()
                WHERE id=:raw_id
            """), {"raw_id": raw["id"]})
        return {
            "status": action, "mbid": mbid, "release_group_id": str(group_id),
            "title": candidate["title"],
            "artist_credits_previewed": len(raw["payload"].get("artist-credit") or []),
            "message": "Release group normalizzato; le singole edizioni restano da acquisire e verificare.",
        }
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Conflitto di integrità; verificare MBID e associazioni.") from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, "Errore durante la normalizzazione del release group.") from exc
