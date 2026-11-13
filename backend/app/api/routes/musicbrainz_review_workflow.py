from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter(
    prefix="/ingestion/musicbrainz/review",
    tags=["ingestion", "review", "workflow"],
)

ENTITY_CONFIG = {
    "artists": {
        "table": "artists",
        "namespace": "MUSICBRAINZ_ARTIST",
        "identifier_column": "artist_id",
        "target_column": "target_artist_id",
    },
    "release_groups": {
        "table": "release_groups",
        "namespace": "MUSICBRAINZ_RELEASE_GROUP",
        "identifier_column": "release_group_id",
        "target_column": "target_release_group_id",
    },
    "releases": {
        "table": "releases",
        "namespace": "MUSICBRAINZ_RELEASE",
        "identifier_column": "release_id",
        "target_column": "target_release_id",
    },
}


class ReviewDecisionRequest(BaseModel):
    action: Literal["APPROVED", "REJECTED", "LINKED"]
    reason: str | None = Field(default=None, max_length=2000)
    reviewer: str | None = Field(default=None, max_length=120)
    target_entity_id: UUID | None = None

    @model_validator(mode="after")
    def validate_action_fields(self):
        if self.action == "REJECTED" and not (self.reason or "").strip():
            raise ValueError("La decisione REJECTED richiede una motivazione.")
        if self.action == "LINKED" and self.target_entity_id is None:
            raise ValueError("La decisione LINKED richiede target_entity_id.")
        if self.action != "LINKED" and self.target_entity_id is not None:
            raise ValueError("target_entity_id è ammesso soltanto per LINKED.")
        if self.reason is not None:
            self.reason = self.reason.strip() or None
        if self.reviewer is not None:
            self.reviewer = self.reviewer.strip() or None
        return self


def _entity_kind(payload) -> str:
    if not isinstance(payload, dict):
        return "unknown"
    if "primary-type" in payload or "secondary-types" in payload:
        return "release_groups"
    if "release-group" in payload or "barcode" in payload or "media" in payload:
        return "releases"
    if "name" in payload and "sort-name" in payload and "type" in payload:
        return "artists"
    return "unknown"


def _record_or_404(db: Session, raw_record_id: UUID, lock: bool = False):
    suffix = " FOR UPDATE OF rr" if lock else ""
    row = db.execute(text(f"""
        SELECT rr.id, rr.ingestion_run_id, rr.source_record_id, rr.payload,
               rr.payload_hash, rr.processing_status, rr.received_at, rr.processed_at
        FROM raw_records rr
        JOIN ingestion_runs ir ON ir.id = rr.ingestion_run_id
        JOIN sources s ON s.id = ir.source_id
        WHERE rr.id = :id AND s.name = 'MusicBrainz'
        {suffix}
    """), {"id": raw_record_id}).mappings().first()
    if row is None:
        raise HTTPException(404, "Record MusicBrainz non trovato.")
    return row


def _decision_history(db: Session, raw_record_id: UUID):
    rows = db.execute(text("""
        SELECT id, raw_record_id, action, entity_kind, reason, reviewer,
               target_artist_id, target_release_group_id, target_release_id, created_at
        FROM musicbrainz_review_decisions
        WHERE raw_record_id = :id
        ORDER BY created_at DESC, id DESC
    """), {"id": raw_record_id}).mappings().all()
    return [dict(row) for row in rows]


@router.get("/decisions")
def list_review_decisions(
    action: str | None = None,
    raw_record_id: UUID | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    if action is not None:
        action = action.upper()
        if action not in {"APPROVED", "REJECTED", "LINKED"}:
            raise HTTPException(422, "Filtro action non valido.")
    rows = db.execute(text("""
        SELECT d.id, d.raw_record_id, rr.source_record_id AS mbid,
               d.action, d.entity_kind, d.reason, d.reviewer,
               d.target_artist_id, d.target_release_group_id,
               d.target_release_id, d.created_at
        FROM musicbrainz_review_decisions d
        JOIN raw_records rr ON rr.id = d.raw_record_id
        WHERE (CAST(:action AS text) IS NULL OR d.action = CAST(:action AS text))
          AND (CAST(:raw_record_id AS uuid) IS NULL OR d.raw_record_id = CAST(:raw_record_id AS uuid))
        ORDER BY d.created_at DESC, d.id DESC
        OFFSET :offset LIMIT :limit
    """), {
        "action": action,
        "raw_record_id": raw_record_id,
        "offset": offset,
        "limit": limit,
    }).mappings().all()
    return {
        "items": [dict(row) for row in rows],
        "returned": len(rows),
        "offset": offset,
        "limit": limit,
        "read_only": True,
    }


@router.get("/records/{raw_record_id}")
def get_review_record(raw_record_id: UUID, db: Session = Depends(get_db)):
    row = _record_or_404(db, raw_record_id)
    kind = _entity_kind(row["payload"])
    link = None
    config = ENTITY_CONFIG.get(kind)
    if config and row["source_record_id"]:
        link = db.execute(text(f"""
            SELECT id, namespace, identifier, {config['identifier_column']} AS target_entity_id
            FROM external_identifiers
            WHERE namespace = :namespace AND identifier = :mbid
        """), {"namespace": config["namespace"], "mbid": row["source_record_id"]}).mappings().first()
    history = _decision_history(db, raw_record_id)
    return {
        "raw_record": {
            "id": str(row["id"]),
            "ingestion_run_id": str(row["ingestion_run_id"]),
            "mbid": row["source_record_id"],
            "entity": kind,
            "payload": row["payload"],
            "payload_hash": row["payload_hash"],
            "processing_status": row["processing_status"],
            "received_at": row["received_at"],
            "processed_at": row["processed_at"],
        },
        "current_external_link": dict(link) if link else None,
        "latest_decision": history[0] if history else None,
        "decision_history": history,
        "raw_payload_immutable": True,
    }


@router.get("/records/{raw_record_id}/decisions")
def get_record_decisions(raw_record_id: UUID, db: Session = Depends(get_db)):
    _record_or_404(db, raw_record_id)
    history = _decision_history(db, raw_record_id)
    return {"raw_record_id": str(raw_record_id), "items": history, "returned": len(history), "read_only": True}


@router.post("/records/{raw_record_id}/decision", status_code=201)
def create_review_decision(
    raw_record_id: UUID,
    request: ReviewDecisionRequest,
    db: Session = Depends(get_db),
):
    """Registra una decisione append-only; il payload raw non viene alterato."""
    db.rollback()
    try:
        with db.begin():
            raw = _record_or_404(db, raw_record_id, lock=True)
            kind = _entity_kind(raw["payload"])
            if kind not in ENTITY_CONFIG:
                raise HTTPException(422, "Il tipo di entità del payload non è supportato per la revisione.")

            target_columns = {
                "target_artist_id": None,
                "target_release_group_id": None,
                "target_release_id": None,
            }
            link_created = False

            if request.action == "LINKED":
                mbid = raw["source_record_id"]
                try:
                    UUID(str(mbid))
                except (ValueError, TypeError):
                    raise HTTPException(422, "Il source_record_id non contiene un MBID valido.")

                config = ENTITY_CONFIG[kind]
                target_id = request.target_entity_id
                exists = db.execute(
                    text(f"SELECT id FROM {config['table']} WHERE id = :id"),
                    {"id": target_id},
                ).scalar_one_or_none()
                if exists is None:
                    raise HTTPException(404, "Entità canonica di destinazione non trovata.")

                existing_link = db.execute(text(f"""
                    SELECT {config['identifier_column']} AS target_id
                    FROM external_identifiers
                    WHERE namespace = :namespace AND identifier = :mbid
                    FOR UPDATE
                """), {"namespace": config["namespace"], "mbid": str(mbid)}).mappings().first()

                if existing_link and existing_link["target_id"] != target_id:
                    raise HTTPException(409, "Questo MBID è già collegato a un'altra entità canonica.")
                if not existing_link:
                    db.execute(text(f"""
                        INSERT INTO external_identifiers(namespace, identifier, {config['identifier_column']})
                        VALUES (:namespace, :mbid, :target_id)
                    """), {"namespace": config["namespace"], "mbid": str(mbid), "target_id": target_id})
                    link_created = True
                target_columns[config["target_column"]] = target_id

            decision = db.execute(text("""
                INSERT INTO musicbrainz_review_decisions
                    (raw_record_id, action, entity_kind, reason, reviewer,
                     target_artist_id, target_release_group_id, target_release_id)
                VALUES
                    (:raw_record_id, :action, :entity_kind, :reason, :reviewer,
                     :target_artist_id, :target_release_group_id, :target_release_id)
                RETURNING id, raw_record_id, action, entity_kind, reason, reviewer,
                          target_artist_id, target_release_group_id, target_release_id, created_at
            """), {
                "raw_record_id": raw_record_id,
                "action": request.action,
                "entity_kind": kind,
                "reason": request.reason,
                "reviewer": request.reviewer or "manual",
                **target_columns,
            }).mappings().one()

        return {
            "decision": dict(decision),
            "external_link_created": link_created,
            "raw_payload_modified": False,
            "normalization_performed": False,
            "message": "Decisione registrata. Il payload originale è stato conservato; nessuna normalizzazione è stata eseguita.",
        }
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Conflitto di integrità durante la registrazione della decisione.") from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, "Errore durante la registrazione della decisione di revisione.") from exc
