from __future__ import annotations
import hashlib, json, os, threading, time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db import get_db

router = APIRouter(prefix="/ingestion", tags=["ingestion"])
_LOCK = threading.Lock()
_LAST = 0.0

def _fetch(mbid: str) -> dict:
    global _LAST
    ua = os.getenv("MUSICBRAINZ_USER_AGENT", "MusicAlmanac/0.7.0 ( https://github.com/santoromarco74/music-almanac )").strip()
    if not ua or ua.lower() in {"python-urllib", "python", "anonymous"}:
        raise HTTPException(500, "Configurare MUSICBRAINZ_USER_AGENT con nome applicazione e contatto.")
    with _LOCK:
        delay = 1.05 - (time.monotonic() - _LAST)
        if delay > 0:
            time.sleep(delay)
        req = Request(f"https://musicbrainz.org/ws/2/artist/{mbid}?fmt=json&inc=aliases+tags",
                      headers={"User-Agent": ua, "Accept": "application/json"})
        try:
            with urlopen(req, timeout=25) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            _LAST = time.monotonic()
            if exc.code == 404: raise HTTPException(404, "MBID non trovato su MusicBrainz.") from exc
            if exc.code == 503: raise HTTPException(503, "MusicBrainz ha limitato la richiesta; riprovare più tardi.") from exc
            raise HTTPException(502, f"Errore HTTP MusicBrainz: {exc.code}.") from exc
        except (URLError, TimeoutError) as exc:
            _LAST = time.monotonic()
            raise HTTPException(502, "MusicBrainz non raggiungibile o timeout.") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            _LAST = time.monotonic()
            raise HTTPException(502, "Risposta MusicBrainz non valida.") from exc
        _LAST = time.monotonic()
        return result

@router.post("/musicbrainz/artists/lookup/{mbid}")
def lookup_artist(mbid: str, db: Session = Depends(get_db)):
    try: UUID(mbid)
    except ValueError as exc: raise HTTPException(422, "MBID non valido.") from exc
    try:
        source = db.execute(text("""
            SELECT id FROM sources WHERE name='MusicBrainz' AND source_type='CATALOG'
            ORDER BY created_at LIMIT 1
        """)).scalar_one_or_none()
        if source is None:
            source = db.execute(text("""
                INSERT INTO sources (name, source_type, base_url, publisher, reliability_tier, license_name, terms_url)
                VALUES ('MusicBrainz','CATALOG','https://musicbrainz.org/','MetaBrainz Foundation',2,
                        'CC0 database; API access terms apply','https://musicbrainz.org/doc/MusicBrainz_API')
                RETURNING id
            """)).scalar_one()
        run_id = db.execute(text("""
            INSERT INTO ingestion_runs (source_id,status) VALUES (:sid,'RUNNING') RETURNING id
        """), {"sid": source}).scalar_one()
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, "Impossibile inizializzare il lookup.") from exc
    try:
        payload = _fetch(mbid)
        if payload.get("id") != mbid:
            raise HTTPException(502, "MusicBrainz ha restituito un MBID differente.")
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        db.execute(text("""
            INSERT INTO raw_records (ingestion_run_id,source_record_id,payload,payload_hash,processing_status)
            VALUES (:rid,:mbid,CAST(:payload AS JSONB),:digest,'PENDING')
        """), {"rid": run_id, "mbid": mbid, "payload": raw,
               "digest": hashlib.sha256(raw.encode("utf-8")).hexdigest()})
        db.execute(text("""
            UPDATE ingestion_runs SET finished_at=now(),status='COMPLETED',
            records_seen=1,records_imported=1,records_rejected=0 WHERE id=:rid
        """), {"rid": run_id})
        db.commit()
        return {"ingestion_run_id": str(run_id), "mbid": mbid, "processing_status": "PENDING",
                "aliases_found": len(payload.get("aliases") or []), "tags_found": len(payload.get("tags") or []),
                "message": "Dettaglio acquisito e conservato in raw_records; non ancora normalizzato."}
    except HTTPException as exc:
        db.rollback()
        db.execute(text("UPDATE ingestion_runs SET finished_at=now(),status='FAILED',error_summary=:e WHERE id=:rid"),
                   {"e": str(exc.detail)[:2000], "rid": run_id})
        db.commit()
        raise
    except Exception as exc:
        db.rollback()
        db.execute(text("UPDATE ingestion_runs SET finished_at=now(),status='FAILED',error_summary=:e WHERE id=:rid"),
                   {"e": str(exc)[:2000], "rid": run_id})
        db.commit()
        raise HTTPException(500, "Errore durante il salvataggio del dettaglio MusicBrainz.") from exc
