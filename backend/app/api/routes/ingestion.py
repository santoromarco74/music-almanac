import hashlib
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter(prefix="/ingestion", tags=["ingestion"])
BASE_URL = "https://musicbrainz.org/ws/2"
DEFAULT_UA = "MusicAlmanac/0.5.0 ( https://github.com/santoromarco74/music-almanac )"


def _user_agent():
    value = os.getenv("MUSICBRAINZ_USER_AGENT", DEFAULT_UA).strip()
    if not value or value.lower() in {"python-urllib", "python", "anonymous"}:
        raise HTTPException(status_code=500, detail="Configurare MUSICBRAINZ_USER_AGENT con nome applicazione, versione e contatto.")
    return value


def _search(query: str, limit: int) -> dict:
    phrase = query.replace("\\", "\\\\").replace('"', '\\"')
    params = urlencode({"query": f'artist:"{phrase}"', "fmt": "json", "limit": limit})
    request = Request(
        f"{BASE_URL}/artist/?{params}",
        headers={"User-Agent": _user_agent(), "Accept": "application/json"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=25) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 503:
            raise HTTPException(status_code=503, detail="MusicBrainz ha limitato la richiesta. Rispettare il limite di una richiesta al secondo.") from exc
        if exc.code == 400:
            raise HTTPException(status_code=422, detail="MusicBrainz ha rifiutato la query.") from exc
        raise HTTPException(status_code=502, detail=f"Errore HTTP MusicBrainz: {exc.code}.") from exc
    except (URLError, TimeoutError) as exc:
        raise HTTPException(status_code=502, detail="MusicBrainz non raggiungibile o timeout.") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=502, detail="Risposta JSON MusicBrainz non valida.") from exc


def _source_id(db: Session):
    found = db.execute(
        text("SELECT id FROM sources WHERE name=:n AND source_type=:t ORDER BY created_at LIMIT 1"),
        {"n": "MusicBrainz", "t": "CATALOG"},
    ).scalar_one_or_none()
    if found:
        return found
    return db.execute(text("""
        INSERT INTO sources
          (name, source_type, base_url, publisher, reliability_tier, license_name, terms_url, notes)
        VALUES
          ('MusicBrainz', 'CATALOG', 'https://musicbrainz.org/', 'MetaBrainz Foundation',
           2, 'CC0 database; API access terms apply',
           'https://musicbrainz.org/doc/MusicBrainz_API',
           'Catalog source; API access subject to MusicBrainz rate limits and terms')
        RETURNING id
    """)).scalar_one()


@router.post("/musicbrainz/artists/search")
def import_artists(
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = q.strip()
    if len(query) < 2:
        raise HTTPException(status_code=422, detail="La query deve contenere almeno due caratteri.")

    try:
        with db.begin():
            source_id = _source_id(db)
            run_id = db.execute(
                text("INSERT INTO ingestion_runs (source_id, status) VALUES (:sid, 'RUNNING') RETURNING id"),
                {"sid": source_id},
            ).scalar_one()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Impossibile inizializzare il job di ingestion.") from exc

    try:
        result = _search(query, limit)
        artists = result.get("artists", [])
        with db.begin():
            for artist in artists:
                raw = json.dumps(artist, ensure_ascii=False, sort_keys=True)
                digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                db.execute(text("""
                    INSERT INTO raw_records
                      (ingestion_run_id, source_record_id, payload, payload_hash, processing_status)
                    VALUES
                      (:rid, :source_id, CAST(:payload AS JSONB), :digest, 'PENDING')
                """), {
                    "rid": run_id,
                    "source_id": artist.get("id"),
                    "payload": raw,
                    "digest": digest,
                })
            db.execute(text("""
                UPDATE ingestion_runs
                SET finished_at=now(), status='COMPLETED',
                    records_seen=:n, records_imported=:n, records_rejected=0
                WHERE id=:rid
            """), {"n": len(artists), "rid": run_id})
        return {
            "ingestion_run_id": str(run_id),
            "source": "MusicBrainz",
            "query": query,
            "records_seen": len(artists),
            "records_imported": len(artists),
            "processing_status": "PENDING",
            "message": "Payload salvati in raw_records; non ancora trasferiti nelle tabelle canoniche.",
        }
    except HTTPException as exc:
        with db.begin():
            db.execute(text("""
                UPDATE ingestion_runs SET finished_at=now(), status='FAILED', error_summary=:err
                WHERE id=:rid
            """), {"err": str(exc.detail)[:2000], "rid": run_id})
        raise
    except Exception as exc:
        db.rollback()
        with db.begin():
            db.execute(text("""
                UPDATE ingestion_runs SET finished_at=now(), status='FAILED', error_summary=:err
                WHERE id=:rid
            """), {"err": str(exc)[:2000], "rid": run_id})
        raise HTTPException(status_code=500, detail="Errore durante la persistenza dei record acquisiti.") from exc
