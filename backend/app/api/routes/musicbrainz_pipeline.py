from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter(prefix="/ingestion/musicbrainz/pipeline", tags=["ingestion", "pipeline"])
_BASE_URL = "https://musicbrainz.org/ws/2"
_RATE_LOCK = threading.Lock()
_LAST_REQUEST = 0.0

ENTITY_CONFIG = {
    "artists": {
        "path": "artist",
        "inc": "aliases+tags",
        "namespace": "MUSICBRAINZ_ARTIST",
    },
    "release_groups": {
        "path": "release-group",
        "inc": "artists+releases",
        "namespace": "MUSICBRAINZ_RELEASE_GROUP",
    },
    "releases": {
        "path": "release",
        "inc": "artists+labels+recordings+release-groups",
        "namespace": "MUSICBRAINZ_RELEASE",
    },
}


class PipelineAcquireRequest(BaseModel):
    artist_mbids: list[UUID] = Field(default_factory=list, max_length=50)
    release_group_mbids: list[UUID] = Field(default_factory=list, max_length=50)
    release_mbids: list[UUID] = Field(default_factory=list, max_length=50)
    execute: bool = False

    @model_validator(mode="after")
    def validate_batch(self):
        total = len(self.artist_mbids) + len(self.release_group_mbids) + len(self.release_mbids)
        if total > 50:
            raise ValueError("Un batch può contenere al massimo 50 MBID.")
        if total == 0:
            raise ValueError("Specificare almeno un MBID.")
        all_ids = (
            [("artists", x) for x in self.artist_mbids]
            + [("release_groups", x) for x in self.release_group_mbids]
            + [("releases", x) for x in self.release_mbids]
        )
        if len({(kind, str(mbid)) for kind, mbid in all_ids}) != len(all_ids):
            raise ValueError("Lo stesso MBID non può essere ripetuto nella medesima categoria.")
        return self


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


def _fetch_musicbrainz(kind: str, mbid: UUID) -> dict:
    global _LAST_REQUEST
    config = ENTITY_CONFIG[kind]
    user_agent = os.getenv(
        "MUSICBRAINZ_USER_AGENT",
        "MusicAlmanac/1.4.0 ( https://github.com/santoromarco74/music-almanac )",
    ).strip()
    if not user_agent or user_agent.lower() in {"python-urllib", "python", "anonymous"}:
        raise HTTPException(500, "Configurare MUSICBRAINZ_USER_AGENT con applicazione, versione e contatto.")
    with _RATE_LOCK:
        delay = 1.05 - (time.monotonic() - _LAST_REQUEST)
        if delay > 0:
            time.sleep(delay)
        url = f"{_BASE_URL}/{config['path']}/{mbid}?inc={config['inc']}&fmt=json"
        request = Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"}, method="GET")
        try:
            with urlopen(request, timeout=25) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            _LAST_REQUEST = time.monotonic()
            if exc.code == 404:
                raise ValueError("MBID non trovato su MusicBrainz.") from exc
            if exc.code == 503:
                raise RuntimeError("MusicBrainz ha limitato la richiesta (HTTP 503).") from exc
            raise RuntimeError(f"Errore HTTP MusicBrainz: {exc.code}.") from exc
        except (URLError, TimeoutError) as exc:
            _LAST_REQUEST = time.monotonic()
            raise RuntimeError("MusicBrainz non raggiungibile o timeout.") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            _LAST_REQUEST = time.monotonic()
            raise RuntimeError("Risposta JSON MusicBrainz non valida.") from exc
        _LAST_REQUEST = time.monotonic()
    if not isinstance(payload, dict) or payload.get("id") != str(mbid):
        raise RuntimeError("Payload MusicBrainz inatteso o MBID non corrispondente.")
    return payload


def _linked(db: Session, kind: str, mbid: str):
    namespace = ENTITY_CONFIG[kind]["namespace"]
    column = {
        "artists": "artist_id",
        "release_groups": "release_group_id",
        "releases": "release_id",
    }[kind]
    return db.execute(text(f"""
        SELECT {column} FROM external_identifiers
        WHERE namespace=:namespace AND identifier=:mbid
    """), {"namespace": namespace, "mbid": mbid}).scalar_one_or_none()


@router.post("/acquire")
def acquire_batch(request: PipelineAcquireRequest, db: Session = Depends(get_db)):
    """Acquisisce record per MBID in un unico batch; la normalizzazione resta manuale."""
    items = (
        [("artists", x) for x in request.artist_mbids]
        + [("release_groups", x) for x in request.release_group_mbids]
        + [("releases", x) for x in request.release_mbids]
    )
    plan = [{"entity": kind, "mbid": str(mbid)} for kind, mbid in items]
    if not request.execute:
        return {
            "mode": "DRY_RUN",
            "items_planned": len(plan),
            "items": plan,
            "normalization_performed": False,
            "message": "Piano validato; nessuna chiamata esterna e nessuna scrittura eseguite. Ripetere con execute=true per acquisire i payload.",
        }

    try:
        source_id = _source_id(db)
        run_id = db.execute(text("""
            INSERT INTO ingestion_runs(source_id,status)
            VALUES (:source_id,'RUNNING') RETURNING id
        """), {"source_id": source_id}).scalar_one()
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, "Impossibile inizializzare il batch di acquisizione.") from exc

    outcomes = []
    imported = 0
    rejected = 0
    for kind, mbid in items:
        try:
            payload = _fetch_musicbrainz(kind, mbid)
            serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
            existing = db.execute(text("""
                SELECT id,processing_status FROM raw_records
                WHERE source_record_id=:mbid AND payload_hash=:digest
                ORDER BY received_at DESC LIMIT 1
            """), {"mbid": str(mbid), "digest": digest}).mappings().first()
            if existing:
                outcomes.append({
                    "entity": kind, "mbid": str(mbid), "status": "DUPLICATE_SKIPPED",
                    "raw_record_id": str(existing["id"]),
                    "processing_status": existing["processing_status"],
                })
                continue
            raw_id = db.execute(text("""
                INSERT INTO raw_records
                  (ingestion_run_id,source_record_id,payload,payload_hash,processing_status)
                VALUES (:run_id,:mbid,CAST(:payload AS JSONB),:digest,'PENDING')
                RETURNING id
            """), {
                "run_id": run_id, "mbid": str(mbid), "payload": serialized, "digest": digest,
            }).scalar_one()
            db.commit()
            imported += 1
            outcomes.append({
                "entity": kind, "mbid": str(mbid), "status": "ACQUIRED",
                "raw_record_id": str(raw_id), "processing_status": "PENDING",
            })
        except ValueError as exc:
            db.rollback()
            rejected += 1
            outcomes.append({"entity": kind, "mbid": str(mbid), "status": "NOT_FOUND", "error": str(exc)})
        except Exception as exc:
            db.rollback()
            rejected += 1
            outcomes.append({"entity": kind, "mbid": str(mbid), "status": "FAILED", "error": str(exc)[:500]})

    try:
        db.execute(text("""
            UPDATE ingestion_runs
            SET finished_at=now(),status=:status,records_seen=:seen,
                records_imported=:imported,records_rejected=:rejected,error_summary=:summary
            WHERE id=:run_id
        """), {
            "status": "COMPLETED" if rejected == 0 else ("PARTIAL" if imported else "FAILED"),
            "seen": len(items), "imported": imported, "rejected": rejected,
            "summary": json.dumps(
                [{"mbid": x["mbid"], "status": x["status"], "error": x.get("error")}
                 for x in outcomes if x["status"] in {"FAILED", "NOT_FOUND"}],
                ensure_ascii=False,
            )[:4000] or None,
            "run_id": run_id,
        })
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, "Acquisizione completata, ma aggiornamento del report batch fallito.") from exc

    return {
        "mode": "EXECUTED",
        "ingestion_run_id": str(run_id),
        "items_seen": len(items),
        "records_imported": imported,
        "records_rejected": rejected,
        "duplicates_skipped": sum(x["status"] == "DUPLICATE_SKIPPED" for x in outcomes),
        "normalization_performed": False,
        "items": outcomes,
        "message": "I payload acquisiti sono in raw_records con stato PENDING. La normalizzazione richiede preview e conferma esplicita per ogni entità.",
    }


@router.get("/runs")
def list_pipeline_runs(
    status: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return db.execute(text("""
        SELECT ir.id,ir.started_at,ir.finished_at,ir.status,
               ir.records_seen,ir.records_imported,ir.records_rejected,ir.error_summary,
               s.name AS source_name
        FROM ingestion_runs ir
        LEFT JOIN sources s ON s.id=ir.source_id
        WHERE (:status IS NULL OR ir.status=:status)
        ORDER BY ir.started_at DESC
        OFFSET :offset LIMIT :limit
    """), {"status": status, "offset": offset, "limit": limit}).mappings().all()


@router.get("/runs/{run_id}")
def get_pipeline_run(run_id: UUID, db: Session = Depends(get_db)):
    run = db.execute(text("""
        SELECT ir.*,s.name AS source_name
        FROM ingestion_runs ir LEFT JOIN sources s ON s.id=ir.source_id
        WHERE ir.id=:id
    """), {"id": run_id}).mappings().first()
    if not run:
        raise HTTPException(404, "Batch di acquisizione non trovato.")
    records = db.execute(text("""
        SELECT id,source_record_id,payload_hash,processing_status,received_at,processed_at,
               payload->>'title' AS title,payload->>'name' AS name
        FROM raw_records WHERE ingestion_run_id=:id
        ORDER BY received_at,id
    """), {"id": run_id}).mappings().all()
    return {"run": dict(run), "records": [dict(x) for x in records]}


@router.get("/quality")
def pipeline_quality_report(db: Session = Depends(get_db)):
    """Report read-only su code, duplicati e dipendenze non risolte."""
    status_rows = db.execute(text("""
        SELECT processing_status,COUNT(*) AS records
        FROM raw_records GROUP BY processing_status ORDER BY processing_status
    """)).mappings().all()
    duplicate_hashes = db.execute(text("""
        SELECT COUNT(*) FROM (
            SELECT payload_hash FROM raw_records
            WHERE payload_hash IS NOT NULL
            GROUP BY payload_hash HAVING COUNT(*) > 1
        ) d
    """)).scalar_one()
    duplicate_mbids = db.execute(text("""
        SELECT COUNT(*) FROM (
            SELECT rr.source_record_id
            FROM raw_records rr
            JOIN ingestion_runs ir ON ir.id=rr.ingestion_run_id
            JOIN sources s ON s.id=ir.source_id
            WHERE s.name='MusicBrainz' AND rr.source_record_id IS NOT NULL
            GROUP BY rr.source_record_id HAVING COUNT(*) > 1
        ) d
    """)).scalar_one()
    unresolved_release_groups = db.execute(text("""
        SELECT COUNT(*) FROM raw_records rr
        JOIN ingestion_runs ir ON ir.id=rr.ingestion_run_id
        JOIN sources s ON s.id=ir.source_id
        WHERE s.name='MusicBrainz'
          AND rr.payload ? 'release-group'
          AND NULLIF(rr.payload->'release-group'->>'id','') IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM external_identifiers ei
              WHERE ei.namespace='MUSICBRAINZ_RELEASE_GROUP'
                AND ei.identifier=rr.payload->'release-group'->>'id'
          )
    """)).scalar_one()
    unresolved_artist_credits = db.execute(text("""
        SELECT COUNT(DISTINCT rr.id)
        FROM raw_records rr
        JOIN ingestion_runs ir ON ir.id=rr.ingestion_run_id
        JOIN sources s ON s.id=ir.source_id
        WHERE s.name='MusicBrainz'
          AND jsonb_typeof(rr.payload->'artist-credit')='array'
          AND EXISTS (
              SELECT 1
              FROM jsonb_array_elements(rr.payload->'artist-credit') ac
              WHERE jsonb_typeof(ac->'artist')='object'
                AND NULLIF(ac->'artist'->>'id','') IS NOT NULL
                AND NOT EXISTS (
                    SELECT 1 FROM external_identifiers ei
                    WHERE ei.namespace='MUSICBRAINZ_ARTIST'
                      AND ei.identifier=ac->'artist'->>'id'
                )
          )
    """)).scalar_one()
    pending = db.execute(text("""
        SELECT COUNT(*) FROM raw_records WHERE processing_status='PENDING'
    """)).scalar_one()
    return {
        "generated_at": db.execute(text("SELECT now()")).scalar_one(),
        "raw_records_by_status": [dict(x) for x in status_rows],
        "pending_records": pending,
        "duplicate_payload_hash_groups": duplicate_hashes,
        "duplicate_musicbrainz_mbid_groups": duplicate_mbids,
        "releases_with_unlinked_release_group": unresolved_release_groups,
        "records_with_unlinked_artist_credits": unresolved_artist_credits,
        "policy": {
            "automatic_deduplication": False,
            "automatic_normalization": False,
            "raw_payloads_are_preserved": True,
            "note": "I conteggi segnalano condizioni da revisionare; non eliminano né modificano record.",
        },
    }
