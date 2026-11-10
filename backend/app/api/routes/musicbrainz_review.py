from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter(
    prefix="/ingestion/musicbrainz/review",
    tags=["ingestion", "review"],
)


def _entity_kind(payload: Any) -> str:
    """Inferisce il tipo di entità dal payload MusicBrainz senza modificarlo."""
    if not isinstance(payload, dict):
        return "unknown"
    if "primary-type" in payload or "secondary-types" in payload:
        return "release_groups"
    if "release-group" in payload or "barcode" in payload or "media" in payload:
        return "releases"
    if "name" in payload and "sort-name" in payload and "type" in payload:
        return "artists"
    return "unknown"


def _musicbrainz_records(db: Session, status: str | None, entity: str, limit: int, offset: int):
    return db.execute(text("""
        SELECT rr.id, rr.ingestion_run_id, rr.source_record_id, rr.payload,
               rr.payload_hash, rr.processing_status, rr.received_at, rr.processed_at
        FROM raw_records rr
        JOIN ingestion_runs ir ON ir.id=rr.ingestion_run_id
        JOIN sources s ON s.id=ir.source_id
        WHERE s.name='MusicBrainz'
          AND (:status IS NULL OR rr.processing_status=:status)
          AND (
            :entity='all'
            OR (:entity='release_groups' AND (rr.payload ? 'primary-type' OR rr.payload ? 'secondary-types'))
            OR (:entity='releases' AND (rr.payload ? 'release-group' OR rr.payload ? 'barcode' OR rr.payload ? 'media'))
            OR (:entity='artists' AND rr.payload ? 'name' AND rr.payload ? 'sort-name' AND rr.payload ? 'type')
            OR (:entity='unknown' AND NOT (
                rr.payload ? 'primary-type' OR rr.payload ? 'secondary-types'
                OR rr.payload ? 'release-group' OR rr.payload ? 'barcode' OR rr.payload ? 'media'
                OR (rr.payload ? 'name' AND rr.payload ? 'sort-name' AND rr.payload ? 'type')
            ))
          )
        ORDER BY rr.received_at DESC, rr.id
        OFFSET :offset LIMIT :limit
    """), {
        "status": status, "entity": entity, "offset": offset, "limit": limit,
    }).mappings().all()


@router.get("/queue")
def review_queue(
    status: str = Query(default="PENDING", min_length=1, max_length=30),
    entity: str = Query(default="all"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Coda di revisione read-only dei payload MusicBrainz non normalizzati."""
    if entity not in {"all", "artists", "release_groups", "releases", "unknown"}:
        raise HTTPException(422, "Filtro entity non valido.")
    status_filter = None if status.lower() == "all" else status.upper()
    rows = _musicbrainz_records(db, status_filter, entity, limit, offset)
    items = []
    for row in rows:
        payload = row["payload"]
        kind = _entity_kind(payload)
        items.append({
            "raw_record_id": str(row["id"]),
            "ingestion_run_id": str(row["ingestion_run_id"]),
            "mbid": row["source_record_id"],
            "entity": kind,
            "title": payload.get("title") if isinstance(payload, dict) else None,
            "name": payload.get("name") if isinstance(payload, dict) else None,
            "payload_hash": row["payload_hash"],
            "processing_status": row["processing_status"],
            "received_at": row["received_at"],
            "processed_at": row["processed_at"],
        })
    return {
        "items": items,
        "returned": len(items),
        "offset": offset,
        "limit": limit,
        "status_filter": status_filter or "ALL",
        "entity_filter": entity,
        "read_only": True,
    }


@router.get("/duplicate-candidates")
def duplicate_candidates(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Propone gruppi di MBID acquisiti più volte; non fonde né elimina record."""
    rows = db.execute(text("""
        WITH duplicate_ids AS (
            SELECT rr.source_record_id
            FROM raw_records rr
            JOIN ingestion_runs ir ON ir.id=rr.ingestion_run_id
            JOIN sources s ON s.id=ir.source_id
            WHERE s.name='MusicBrainz' AND rr.source_record_id IS NOT NULL
            GROUP BY rr.source_record_id
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC, rr.source_record_id
            LIMIT :limit
        )
        SELECT rr.id, rr.source_record_id, rr.payload, rr.payload_hash,
               rr.processing_status, rr.received_at
        FROM raw_records rr
        JOIN ingestion_runs ir ON ir.id=rr.ingestion_run_id
        JOIN sources s ON s.id=ir.source_id
        JOIN duplicate_ids d ON d.source_record_id=rr.source_record_id
        WHERE s.name='MusicBrainz'
        ORDER BY rr.source_record_id, rr.received_at, rr.id
    """), {"limit": limit}).mappings().all()

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        kind = _entity_kind(row["payload"])
        key = (kind, row["source_record_id"])
        grouped[key].append({
            "raw_record_id": str(row["id"]),
            "payload_hash": row["payload_hash"],
            "processing_status": row["processing_status"],
            "received_at": row["received_at"],
        })

    candidates = []
    for (kind, mbid), records in grouped.items():
        if len(records) < 2:
            continue
        hashes = {record["payload_hash"] for record in records}
        candidates.append({
            "mbid": mbid,
            "entity": kind,
            "records": records,
            "record_count": len(records),
            "identical_payloads": len(hashes) == 1,
            "distinct_payload_versions": len(hashes),
            "recommendation": (
                "Verificare duplicazione tecnica; payload identici"
                if len(hashes) == 1
                else "Confrontare le versioni: il payload è cambiato tra acquisizioni"
            ),
        })

    return {
        "candidates": candidates,
        "candidate_groups": len(candidates),
        "automatic_deduplication": False,
        "read_only": True,
        "note": "I gruppi sono suggerimenti di revisione. Nessun raw_record viene eliminato o modificato.",
    }


@router.get("/dependencies")
def unresolved_dependencies(
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Elenca release in coda con release group o crediti artista non collegati."""
    rows = db.execute(text("""
        SELECT rr.id, rr.source_record_id, rr.payload, rr.processing_status,
               rr.received_at
        FROM raw_records rr
        JOIN ingestion_runs ir ON ir.id=rr.ingestion_run_id
        JOIN sources s ON s.id=ir.source_id
        WHERE s.name='MusicBrainz' AND rr.processing_status='PENDING'
        ORDER BY rr.received_at, rr.id
        LIMIT :limit
    """), {"limit": limit}).mappings().all()

    release_group_mbids: set[str] = set()
    artist_mbids: set[str] = set()
    candidates = []
    for row in rows:
        payload = row["payload"]
        if _entity_kind(payload) != "releases":
            continue
        group = payload.get("release-group") if isinstance(payload, dict) else None
        group_mbid = group.get("id") if isinstance(group, dict) else None
        credits = payload.get("artist-credit") or []
        credit_mbids = []
        if isinstance(credits, list):
            for credit in credits:
                if isinstance(credit, dict) and isinstance(credit.get("artist"), dict):
                    mbid = credit["artist"].get("id")
                    if mbid:
                        credit_mbids.append(str(mbid))
        if group_mbid:
            release_group_mbids.add(str(group_mbid))
        artist_mbids.update(credit_mbids)
        candidates.append({
            "raw_record_id": str(row["id"]),
            "mbid": row["source_record_id"],
            "title": payload.get("title"),
            "release_group_mbid": str(group_mbid) if group_mbid else None,
            "artist_mbids": list(dict.fromkeys(credit_mbids)),
            "received_at": row["received_at"],
        })

    linked_groups = set()
    linked_artists = set()
    if release_group_mbids:
        linked_groups = set(db.execute(text("""
            SELECT identifier FROM external_identifiers
            WHERE namespace='MUSICBRAINZ_RELEASE_GROUP'
              AND identifier = ANY(CAST(:ids AS text[]))
        """), {"ids": list(release_group_mbids)}).scalars().all())
    if artist_mbids:
        linked_artists = set(db.execute(text("""
            SELECT identifier FROM external_identifiers
            WHERE namespace='MUSICBRAINZ_ARTIST'
              AND identifier = ANY(CAST(:ids AS text[]))
        """), {"ids": list(artist_mbids)}).scalars().all())

    items = []
    for candidate in candidates:
        group_mbid = candidate["release_group_mbid"]
        missing_artists = [mbid for mbid in candidate["artist_mbids"] if mbid not in linked_artists]
        group_linked = group_mbid in linked_groups if group_mbid else False
        items.append({
            **candidate,
            "release_group_linked": group_linked,
            "unlinked_artist_mbids": missing_artists,
            "dependencies_resolved": bool(group_linked) and not missing_artists,
            "normalization_order": "RELEASE_GROUP_THEN_ARTISTS_THEN_RELEASE",
        })

    return {
        "items": items,
        "release_records_reviewed": len(items),
        "records_with_unlinked_release_group": sum(not x["release_group_linked"] for x in items),
        "records_with_unlinked_artists": sum(bool(x["unlinked_artist_mbids"]) for x in items),
        "automatic_linking": False,
        "read_only": True,
        "note": "La risoluzione delle dipendenze richiede collegamenti espliciti e revisione editoriale.",
    }
