from __future__ import annotations

import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter(prefix="/ingestion", tags=["ingestion"])

# MusicBrainz artist type -> local canonical artist_type.
ARTIST_TYPE_MAP = {
    "person": "PERSON",
    "group": "GROUP",
    "orchestra": "ORCHESTRA",
    "choir": "CHOIR",
    "character": "CHARACTER",
    "other": "OTHER",
}


class NormalizeArtistRequest(BaseModel):
    # Required only when a same-name local artist already exists.
    # This is an explicit editorial decision to link the MBID to that artist.
    existing_artist_id: UUID | None = None


def _normalized_artist(payload: dict) -> dict:
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        raise HTTPException(status_code=422, detail="Il payload MusicBrainz non contiene un nome valido.")

    raw_type = payload.get("type")
    artist_type = ARTIST_TYPE_MAP.get(str(raw_type).strip().lower(), "OTHER")

    life_span = payload.get("life-span") or {}
    begin = life_span.get("begin")
    end = life_span.get("end")

    def year(value):
        if not isinstance(value, str) or not re.match(r"^\d{4}", value):
            return None
        return int(value[:4])

    # MusicBrainz `country` is an ISO country code. `area` is a geographic
    # subdivision (e.g. England) and must not be mistaken for a country code.
    country = payload.get("country")
    country_code = country.upper() if isinstance(country, str) and re.fullmatch(r"[A-Za-z]{2}", country) else None

    return {
        "canonical_name": name.strip(),
        "sort_name": payload.get("sort-name") or None,
        "artist_type": artist_type,
        "country_code": country_code,
        "begin_year": year(begin),
        "end_year": year(end),
        "biography": None,
        "disambiguation": payload.get("disambiguation") or None,
    }


def _raw_record(db: Session, mbid: str):
    row = db.execute(text("""
        SELECT rr.id, rr.payload, rr.processing_status
        FROM raw_records rr
        JOIN ingestion_runs ir ON ir.id = rr.ingestion_run_id
        JOIN sources s ON s.id = ir.source_id
        WHERE rr.source_record_id = :mbid
          AND s.name = 'MusicBrainz'
          AND s.source_type = 'CATALOG'
        ORDER BY rr.received_at DESC
        LIMIT 1
    """), {"mbid": mbid}).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Record MusicBrainz non trovato in raw_records.")
    return row


def _existing_identifier(db: Session, mbid: str):
    return db.execute(text("""
        SELECT artist_id
        FROM external_identifiers
        WHERE namespace = 'MUSICBRAINZ_ARTIST' AND identifier = :mbid
    """), {"mbid": mbid}).scalar_one_or_none()


@router.get("/musicbrainz/artists/preview/{mbid}")
def preview_musicbrainz_artist(mbid: str, db: Session = Depends(get_db)):
    try:
        UUID(mbid)
    except ValueError:
        raise HTTPException(status_code=422, detail="MBID non valido.")

    raw = _raw_record(db, mbid)
    candidate = _normalized_artist(raw["payload"])
    matches = db.execute(text("""
        SELECT id, canonical_name, artist_type
        FROM artists
        WHERE lower(canonical_name) = lower(:name)
        ORDER BY id
    """), {"name": candidate["canonical_name"]}).mappings().all()

    linked_artist_id = _existing_identifier(db, mbid)
    return {
        "mbid": mbid,
        "raw_record_id": str(raw["id"]),
        "processing_status": raw["processing_status"],
        "normalized_candidate": candidate,
        "existing_artist_matches": [
            {"id": str(item["id"]), "canonical_name": item["canonical_name"], "artist_type": item["artist_type"]}
            for item in matches
        ],
        "already_linked_artist_id": str(linked_artist_id) if linked_artist_id else None,
        "notes": [
            "Il campo area non viene convertito in country_code.",
            "Alias e tag restano nel payload grezzo: non esistono ancora tabelle canoniche dedicate.",
            "La data viene ridotta all'anno nella tabella artists; il payload originale conserva la precisione completa.",
        ],
    }


@router.post("/musicbrainz/artists/normalize/{mbid}")
def normalize_musicbrainz_artist(
    mbid: str,
    request: NormalizeArtistRequest,
    db: Session = Depends(get_db),
):
    try:
        UUID(mbid)
    except ValueError:
        raise HTTPException(status_code=422, detail="MBID non valido.")

    try:
        raw = _raw_record(db, mbid)
        candidate = _normalized_artist(raw["payload"])

        linked_artist_id = _existing_identifier(db, mbid)
        if linked_artist_id:
            return {
                "status": "ALREADY_LINKED",
                "mbid": mbid,
                "artist_id": str(linked_artist_id),
                "message": "Questo MBID è già associato a un artista canonico.",
            }

        if request.existing_artist_id is not None:
            artist_exists = db.execute(
                text("SELECT id FROM artists WHERE id = :id"),
                {"id": request.existing_artist_id},
            ).scalar_one_or_none()
            if artist_exists is None:
                raise HTTPException(status_code=404, detail="L'artista canonico indicato non esiste.")
            artist_id = request.existing_artist_id
            action = "LINKED_TO_EXISTING"
        else:
            matches = db.execute(text("""
                SELECT id, canonical_name, artist_type
                FROM artists
                WHERE lower(canonical_name) = lower(:name)
                ORDER BY id
            """), {"name": candidate["canonical_name"]}).mappings().all()

            if matches:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Esiste già uno o più artisti con lo stesso nome. Selezionare esplicitamente l'artista da collegare oppure risolvere il duplicato.",
                        "candidate_matches": [
                            {"id": str(item["id"]), "canonical_name": item["canonical_name"], "artist_type": item["artist_type"]}
                            for item in matches
                        ],
                    },
                )

            artist_id = db.execute(text("""
                INSERT INTO artists
                  (canonical_name, sort_name, artist_type, country_code,
                   begin_year, end_year, biography, disambiguation)
                VALUES
                  (:canonical_name, :sort_name, :artist_type, :country_code,
                   :begin_year, :end_year, :biography, :disambiguation)
                RETURNING id
            """), candidate).scalar_one()
            action = "CREATED"

        db.execute(text("""
            INSERT INTO external_identifiers (namespace, identifier, artist_id)
            VALUES ('MUSICBRAINZ_ARTIST', :mbid, :artist_id)
        """), {"mbid": mbid, "artist_id": artist_id})

        db.execute(text("""
            UPDATE raw_records
            SET processing_status = 'PROCESSED', processed_at = now()
            WHERE id = :raw_id
        """), {"raw_id": raw["id"]})

        db.commit()
        return {
            "status": action,
            "mbid": mbid,
            "artist_id": str(artist_id),
            "canonical_name": candidate["canonical_name"],
            "message": "Normalizzazione completata; payload originale conservato in raw_records.",
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Errore durante la normalizzazione dell'artista.") from exc
