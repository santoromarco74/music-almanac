from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from datetime import date
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

router = APIRouter(prefix="/ingestion/musicbrainz/releases", tags=["ingestion"])
_BASE_URL = "https://musicbrainz.org/ws/2"
_RATE_LOCK = threading.Lock()
_LAST_REQUEST = 0.0
STATUSES = {"VERIFIED", "CONFIRMED", "PRELIMINARY", "TO_VERIFY", "UNCERTAIN"}


def _musicbrainz_get(path: str, params: dict) -> dict:
    global _LAST_REQUEST
    user_agent = os.getenv(
        "MUSICBRAINZ_USER_AGENT",
        "MusicAlmanac/1.3.0 ( https://github.com/santoromarco74/music-almanac )",
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
                raise HTTPException(404, "Release non trovata su MusicBrainz.") from exc
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


def _persist_records(db: Session, records: list[dict]):
    source_id = _source_id(db)
    run_id = db.execute(text("""
        INSERT INTO ingestion_runs(source_id,status)
        VALUES (:source_id,'RUNNING') RETURNING id
    """), {"source_id": source_id}).scalar_one()
    imported = 0
    rejected = 0
    for payload in records:
        mbid = payload.get("id") if isinstance(payload, dict) else None
        if not isinstance(mbid, str):
            rejected += 1
            continue
        raw_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
        db.execute(text("""
            INSERT INTO raw_records
              (ingestion_run_id,source_record_id,payload,payload_hash,processing_status)
            VALUES (:run_id,:mbid,CAST(:payload AS JSONB),:digest,'PENDING')
        """), {"run_id": run_id, "mbid": mbid, "payload": raw_json, "digest": digest})
        imported += 1
    db.execute(text("""
        UPDATE ingestion_runs
        SET finished_at=now(),status='COMPLETED',records_seen=:seen,
            records_imported=:imported,records_rejected=:rejected
        WHERE id=:run_id
    """), {"seen": len(records), "imported": imported, "rejected": rejected, "run_id": run_id})
    return run_id, imported, rejected


def _validate_mbid(mbid: str) -> None:
    try:
        UUID(mbid)
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(422, "MBID non valido.") from exc


def _raw(db: Session, mbid: str, lock: bool = False):
    suffix = " FOR UPDATE OF rr" if lock else ""
    item = db.execute(text(f"""
        SELECT rr.id,rr.payload,rr.processing_status,rr.ingestion_run_id
        FROM raw_records rr
        JOIN ingestion_runs ir ON ir.id=rr.ingestion_run_id
        JOIN sources s ON s.id=ir.source_id
        WHERE rr.source_record_id=:mbid
          AND s.name='MusicBrainz' AND s.source_type='CATALOG'
        ORDER BY rr.received_at DESC,rr.id DESC
        LIMIT 1{suffix}
    """), {"mbid": mbid}).mappings().first()
    if item is None:
        raise HTTPException(404, "Release non presente in raw_records; eseguire prima search o lookup.")
    return item


def _partial_date(value: str | None):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", value):
        return {"release_year": None, "release_month": None, "release_day": None,
                "date_precision": "YEAR", "release_date": None, "date_text": value or None}
    parts = value.split("-")
    year = int(parts[0])
    if len(parts) == 1:
        return {"release_year": year, "release_month": None, "release_day": None,
                "date_precision": "YEAR", "release_date": None, "date_text": value}
    month = int(parts[1])
    if len(parts) == 2:
        if not 1 <= month <= 12:
            raise HTTPException(422, "Mese MusicBrainz non valido.")
        return {"release_year": year, "release_month": month, "release_day": None,
                "date_precision": "MONTH", "release_date": None, "date_text": value}
    day = int(parts[2])
    try:
        full_date = date(year, month, day)
    except ValueError as exc:
        raise HTTPException(422, "Data MusicBrainz non valida.") from exc
    return {"release_year": year, "release_month": month, "release_day": day,
            "date_precision": "DAY", "release_date": full_date, "date_text": value}


def _candidate(payload: dict) -> dict:
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        raise HTTPException(422, "Il payload MusicBrainz non contiene un titolo valido.")
    country = payload.get("country")
    country_code = country.upper() if isinstance(country, str) and re.fullmatch(r"[A-Za-z]{2}", country) else None
    media = payload.get("media") or []
    formats = list(dict.fromkeys(
        str(item.get("format")).strip() for item in media
        if isinstance(item, dict) and item.get("format")
    ))
    label_info = []
    for item in payload.get("label-info") or []:
        if not isinstance(item, dict):
            continue
        label = item.get("label") or {}
        if isinstance(label, dict) and label.get("name"):
            label_info.append({
                "name": str(label["name"]).strip(),
                "catalog_number": item.get("catalog-number"),
                "label_mbid": label.get("id"),
            })
    catalog_numbers = list(dict.fromkeys(
        str(item.get("catalog_number")).strip() for item in label_info
        if item.get("catalog_number")
    ))
    rg = payload.get("release-group") or {}
    rg_mbid = rg.get("id") if isinstance(rg, dict) else None
    return {
        "title": title.strip(),
        "country_code": country_code,
        **_partial_date(payload.get("date")),
        "barcode": payload.get("barcode") or None,
        "format": "; ".join(formats) or None,
        "catalog_number": "; ".join(catalog_numbers) or None,
        "release_group_mbid": rg_mbid,
        "label_info": label_info,
        "media_count": len(media) if isinstance(media, list) else 0,
    }


def _artist_credits(db: Session, payload: dict) -> list[dict]:
    result = []
    seen = set()
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
        # La PK di release_artists non consente crediti duplicati per artista/ruolo.
        # Manteniamo la prima occorrenza, preservando il credito testuale.
        if artist_id and str(artist_id) not in seen:
            result.append({
                "artist_id": artist_id,
                "credited_as": item.get("name") or artist.get("name") or None,
                "position": len(result) + 1,
            })
            seen.add(str(artist_id))
    return result


def _linked_release(db: Session, mbid: str):
    return db.execute(text("""
        SELECT release_id FROM external_identifiers
        WHERE namespace='MUSICBRAINZ_RELEASE' AND identifier=:mbid
    """), {"mbid": mbid}).scalar_one_or_none()


class NormalizeReleaseRequest(BaseModel):
    existing_release_id: UUID | None = None
    release_group_id: UUID | None = None
    label_id: UUID | None = None
    status: str = "TO_VERIFY"


@router.post("/search")
def search_releases(
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = q.strip()
    if len(query) < 2:
        raise HTTPException(422, "La query deve contenere almeno due caratteri.")
    escaped = query.replace("\\", "\\\\").replace('"', '\\"')
    result = _musicbrainz_get("release/", {"query": f'release:"{escaped}"', "limit": limit})
    releases = result.get("releases") or []
    if not isinstance(releases, list):
        raise HTTPException(502, "Risposta MusicBrainz priva di una lista releases valida.")
    try:
        with db.begin():
            run_id, imported, rejected = _persist_records(db, releases)
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, "Errore durante la persistenza dei risultati MusicBrainz.") from exc
    return {
        "ingestion_run_id": str(run_id), "source": "MusicBrainz", "query": query,
        "records_seen": len(releases), "records_imported": imported, "records_rejected": rejected,
        "processing_status": "PENDING", "results": releases,
        "message": "Risultati conservati in raw_records; nessuna edizione canonica è stata creata.",
    }


@router.post("/lookup/{mbid}")
def lookup_release(mbid: str, db: Session = Depends(get_db)):
    _validate_mbid(mbid)
    payload = _musicbrainz_get(f"release/{mbid}", {
        "inc": "artists+labels+recordings+release-groups",
    })
    if payload.get("id") != mbid:
        raise HTTPException(502, "MusicBrainz ha restituito un MBID differente.")
    try:
        with db.begin():
            run_id, imported, rejected = _persist_records(db, [payload])
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, "Errore durante il salvataggio della release.") from exc
    return {
        "ingestion_run_id": str(run_id), "mbid": mbid, "processing_status": "PENDING",
        "records_imported": imported, "records_rejected": rejected,
        "message": "Dettaglio acquisito e conservato in raw_records; non ancora normalizzato.",
    }


@router.get("/preview/{mbid}")
def preview_release(mbid: str, db: Session = Depends(get_db)):
    _validate_mbid(mbid)
    raw = _raw(db, mbid)
    candidate = _candidate(raw["payload"])
    linked = _linked_release(db, mbid)
    group_id = None
    if candidate["release_group_mbid"]:
        group_id = db.execute(text("""
            SELECT release_group_id FROM external_identifiers
            WHERE namespace='MUSICBRAINZ_RELEASE_GROUP' AND identifier=:mbid
        """), {"mbid": candidate["release_group_mbid"]}).scalar_one_or_none()
    matches = db.execute(text("""
        SELECT id,title,country_code,release_year,release_month,release_day,catalog_number
        FROM releases
        WHERE lower(title)=lower(:title)
          AND (CAST(:country AS CHAR(2)) IS NULL OR country_code=:country)
          AND (CAST(:year AS SMALLINT) IS NULL OR release_year=:year)
        ORDER BY id
    """), {"title": candidate["title"], "country": candidate["country_code"],
           "year": candidate["release_year"]}).mappings().all()
    label_matches = []
    for label in candidate["label_info"]:
        rows = db.execute(text("""
            SELECT id,name,country_code FROM labels
            WHERE lower(name)=lower(:name)
              AND (country_code IS NOT DISTINCT FROM CAST(:country AS CHAR(2)))
            ORDER BY id
        """), {"name": label["name"], "country": candidate["country_code"]}).mappings().all()
        label_matches.append({
            **label,
            "local_matches": [{"id": str(x["id"]), "name": x["name"],
                               "country_code": x["country_code"]} for x in rows],
        })
    return {
        "mbid": mbid, "raw_record_id": str(raw["id"]),
        "processing_status": raw["processing_status"], "normalized_candidate": candidate,
        "already_linked_release_id": str(linked) if linked else None,
        "release_group_local_id": str(group_id) if group_id else None,
        "existing_release_matches": [
            {"id": str(x["id"]), "title": x["title"], "country_code": x["country_code"],
             "release_year": x["release_year"], "release_month": x["release_month"],
             "release_day": x["release_day"], "catalog_number": x["catalog_number"]}
            for x in matches
        ],
        "labels": label_matches,
        "artist_credits_linkable": _artist_credits(db, raw["payload"]),
        "artist_credit_count": len(raw["payload"].get("artist-credit") or []),
        "notes": [
            "Release e release group sono entità distinte: il gruppo deve essere già collegato o selezionato esplicitamente.",
            "Le etichette non vengono create automaticamente; label_id può essere indicato in normalize.",
            "Sono associati soltanto artisti con MBID già collegato a un artista canonico.",
            "Le date parziali mantengono la precisione YEAR, MONTH o DAY.",
            "Il payload originale resta conservato in raw_records.",
        ],
    }


@router.post("/normalize/{mbid}")
def normalize_release(
    mbid: str,
    request: NormalizeReleaseRequest,
    db: Session = Depends(get_db),
):
    _validate_mbid(mbid)
    db.rollback()
    try:
        with db.begin():
            raw = _raw(db, mbid, lock=True)
            payload = raw["payload"]
            candidate = _candidate(payload)
            linked = _linked_release(db, mbid)
            status_value = str(request.status or "TO_VERIFY").upper()
            if status_value not in STATUSES:
                raise HTTPException(422, "verification_status non valido.")

            source_id = db.execute(text("""
                SELECT source_id FROM ingestion_runs WHERE id=:id
            """), {"id": raw["ingestion_run_id"]}).scalar_one_or_none()

            if linked:
                release_id, action = linked, "ALREADY_LINKED"
            elif request.existing_release_id:
                release_id = request.existing_release_id
                exists = db.execute(text("SELECT id FROM releases WHERE id=:id"),
                                    {"id": release_id}).scalar_one_or_none()
                if not exists:
                    raise HTTPException(404, "Release canonica indicata non esistente.")
                action = "LINKED_TO_EXISTING"
                db.execute(text("""
                    INSERT INTO external_identifiers(namespace,identifier,release_id)
                    VALUES ('MUSICBRAINZ_RELEASE',:mbid,:release_id)
                """), {"mbid": mbid, "release_id": release_id})
            else:
                group_id = request.release_group_id
                if group_id is None and candidate["release_group_mbid"]:
                    group_id = db.execute(text("""
                        SELECT release_group_id FROM external_identifiers
                        WHERE namespace='MUSICBRAINZ_RELEASE_GROUP' AND identifier=:mbid
                    """), {"mbid": candidate["release_group_mbid"]}).scalar_one_or_none()
                if group_id is None:
                    raise HTTPException(409, detail={
                        "message": "Release group non collegato: normalizzarlo prima oppure indicare release_group_id.",
                        "release_group_mbid": candidate["release_group_mbid"],
                    })
                if not db.execute(text("SELECT 1 FROM release_groups WHERE id=:id"),
                                  {"id": group_id}).scalar_one_or_none():
                    raise HTTPException(404, "Release group canonico indicato non esistente.")

                label_id = request.label_id
                if label_id is not None:
                    if not db.execute(text("SELECT 1 FROM labels WHERE id=:id"),
                                      {"id": label_id}).scalar_one_or_none():
                        raise HTTPException(404, "Etichetta canonica indicata non esistente.")
                elif candidate["label_info"]:
                    first = candidate["label_info"][0]
                    rows = db.execute(text("""
                        SELECT id FROM labels
                        WHERE lower(name)=lower(:name)
                          AND country_code IS NOT DISTINCT FROM CAST(:country AS CHAR(2))
                        ORDER BY id
                    """), {"name": first["name"], "country": candidate["country_code"]}).scalars().all()
                    if len(rows) == 1:
                        label_id = rows[0]
                    elif len(rows) > 1:
                        raise HTTPException(409, detail={
                            "message": "Etichetta omonima ambigua: indicare label_id oppure lasciare label_id nullo.",
                            "label_name": first["name"],
                            "candidate_label_ids": [str(x) for x in rows],
                        })

                release_id = db.execute(text("""
                    INSERT INTO releases(
                      release_group_id,title,country_code,release_date,release_year,
                      release_month,release_day,date_precision,label_id,catalog_number,
                      format,barcode,status,notes
                    ) VALUES (
                      :group_id,:title,:country,:release_date,:year,:month,
                      :day,CAST(:precision AS date_precision),:label_id,:catalog,
                      :format,:barcode,CAST(:status AS verification_status),:notes
                    ) RETURNING id
                """), {
                    "group_id": group_id, "title": candidate["title"],
                    "country": candidate["country_code"], "release_date": candidate["release_date"],
                    "year": candidate["release_year"], "month": candidate["release_month"],
                    "day": candidate["release_day"], "precision": candidate["date_precision"],
                    "label_id": label_id, "catalog": candidate["catalog_number"],
                    "format": candidate["format"], "barcode": candidate["barcode"],
                    "status": status_value,
                    "notes": "Importazione MusicBrainz; payload integrale conservato in raw_records.",
                }).scalar_one()

                for credit in _artist_credits(db, payload):
                    db.execute(text("""
                        INSERT INTO release_artists(release_id,artist_id,credited_as,credit_role,position)
                        VALUES (:release_id,:artist_id,:credited_as,'PRIMARY',:position)
                        ON CONFLICT (release_id,artist_id,credit_role)
                        DO UPDATE SET credited_as=EXCLUDED.credited_as,position=EXCLUDED.position
                    """), {"release_id": release_id, **credit})

                db.execute(text("""
                    INSERT INTO external_identifiers(namespace,identifier,release_id)
                    VALUES ('MUSICBRAINZ_RELEASE',:mbid,:release_id)
                """), {"mbid": mbid, "release_id": release_id})
                db.execute(text("""
                    INSERT INTO entity_sources(source_id,release_id,evidence_url,evidence_note,status)
                    VALUES (:source_id,:release_id,:url,:note,'PRELIMINARY')
                """), {
                    "source_id": source_id, "release_id": release_id,
                    "url": f"https://musicbrainz.org/release/{mbid}",
                    "note": "Dati acquisiti tramite MusicBrainz API; verifica editoriale non ancora completata.",
                })
                if candidate["release_year"] is not None:
                    db.execute(text("""
                        INSERT INTO date_assertions(
                          source_id,subject_kind,release_id,asserted_year,asserted_month,
                          asserted_day,precision,status,evidence_url,evidence_note
                        ) VALUES (
                          :source_id,'RELEASE',:release_id,:year,:month,:day,
                          CAST(:precision AS date_precision),'PRELIMINARY',:url,:note
                        )
                    """), {
                        "source_id": source_id, "release_id": release_id,
                        "year": candidate["release_year"], "month": candidate["release_month"],
                        "day": candidate["release_day"], "precision": candidate["date_precision"],
                        "url": f"https://musicbrainz.org/release/{mbid}",
                        "note": "Data dichiarata da MusicBrainz; asserzione separata dal dato canonico.",
                    })
                action = "CREATED"

            db.execute(text("""
                UPDATE raw_records SET processing_status='PROCESSED',processed_at=now()
                WHERE id=:id
            """), {"id": raw["id"]})

        return {
            "status": action, "mbid": mbid, "release_id": str(release_id),
            "title": candidate["title"],
            "message": "Release collegata o normalizzata; payload originale e provenienza conservati.",
        }
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Conflitto di integrità; verificare MBID, release group, label e crediti artista.") from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, "Errore durante la normalizzazione della release.") from exc
