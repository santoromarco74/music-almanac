from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter(tags=["awards"])


def one(db: Session, sql: str, params: dict | None = None):
    row = db.execute(text(sql), params or {}).mappings().first()
    return dict(row) if row else None


def get_award_or_404(db: Session, award_id: UUID):
    result = one(
        db,
        """SELECT a.*, e.title AS event_title, e.event_year, e.event_month, e.event_day
           FROM awards a LEFT JOIN events e ON e.id = a.event_id
           WHERE a.id = :id""",
        {"id": award_id},
    )
    if not result:
        raise HTTPException(404, "Riconoscimento non trovato.")
    return result


def validate_payload(name, edition_year, event_id, db: Session):
    if not isinstance(name, str) or not name.strip():
        raise HTTPException(422, "name obbligatorio e non può essere vuoto.")
    if edition_year is not None:
        if isinstance(edition_year, bool) or not isinstance(edition_year, int) or not 1 <= edition_year <= 32767:
            raise HTTPException(422, "edition_year deve essere un intero compreso tra 1 e 32767.")
    if event_id is not None:
        try:
            event_id = UUID(str(event_id))
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, "event_id deve essere un UUID valido.") from exc
        event = one(
            db,
            "SELECT id, event_type, event_year FROM events WHERE id = CAST(:id AS UUID)",
            {"id": event_id},
        )
        if not event:
            raise HTTPException(422, "event_id non corrisponde a un evento esistente.")
        if event["event_type"] != "AWARD":
            raise HTTPException(422, "L'evento associato deve avere event_type='AWARD'.")
        if edition_year is not None and event["event_year"] is not None and event["event_year"] != edition_year:
            raise HTTPException(422, "edition_year deve essere coerente con l'anno dell'evento associato.")


@router.get("/awards")
def list_awards(
    q: str | None = None,
    awarding_body: str | None = None,
    category: str | None = None,
    edition_year: int | None = None,
    event_id: UUID | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text(
            """SELECT a.*, e.title AS event_title
               FROM awards a LEFT JOIN events e ON e.id = a.event_id
               WHERE (CAST(:q AS TEXT) IS NULL OR a.name ILIKE '%' || :q || '%')
                 AND (CAST(:body AS TEXT) IS NULL OR a.awarding_body ILIKE '%' || :body || '%')
                 AND (CAST(:category AS TEXT) IS NULL OR a.category ILIKE '%' || :category || '%')
                 AND (CAST(:year AS SMALLINT) IS NULL OR a.edition_year = :year)
                 AND (CAST(:event AS UUID) IS NULL OR a.event_id = :event)
               ORDER BY a.edition_year DESC NULLS LAST, lower(a.name), lower(COALESCE(a.category, ''))
               OFFSET :offset LIMIT :limit"""
        ),
        {
            "q": q,
            "body": awarding_body,
            "category": category,
            "year": edition_year,
            "event": event_id,
            "offset": offset,
            "limit": limit,
        },
    ).mappings().all()
    return [dict(row) for row in rows]


@router.post("/awards", status_code=201)
def create_award(payload: dict, db: Session = Depends(get_db)):
    name = payload.get("name")
    awarding_body = payload.get("awarding_body")
    category = payload.get("category")
    edition_year = payload.get("edition_year")
    event_id = payload.get("event_id")
    validate_payload(name, edition_year, event_id, db)
    try:
        result = one(
            db,
            """INSERT INTO awards(name, awarding_body, category, edition_year, event_id)
               VALUES (:name, :body, :category, :year, CAST(:event AS UUID))
               RETURNING *""",
            {
                "name": name.strip(),
                "body": awarding_body.strip() if isinstance(awarding_body, str) else awarding_body,
                "category": category.strip() if isinstance(category, str) else category,
                "year": edition_year,
                "event": event_id,
            },
        )
        db.commit()
        return result
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(422, "Dati o riferimenti del riconoscimento non validi.") from exc


@router.get("/awards/{award_id}")
def get_award(award_id: UUID, db: Session = Depends(get_db)):
    return get_award_or_404(db, award_id)


@router.patch("/awards/{award_id}")
def update_award(award_id: UUID, payload: dict, db: Session = Depends(get_db)):
    old = get_award_or_404(db, award_id)
    allowed = {"name", "awarding_body", "category", "edition_year", "event_id"}
    changes = {key: value for key, value in payload.items() if key in allowed}
    if not changes:
        return old

    merged = {**old, **changes}
    validate_payload(merged.get("name"), merged.get("edition_year"), merged.get("event_id"), db)
    if "name" in changes:
        changes["name"] = changes["name"].strip()
    for key in ("awarding_body", "category"):
        if key in changes and isinstance(changes[key], str):
            changes[key] = changes[key].strip() or None

    assignments = []
    params = {"id": award_id}
    for key, value in changes.items():
        if key == "event_id":
            assignments.append("event_id = CAST(:event_id AS UUID)")
        else:
            assignments.append(f"{key} = :{key}")
        params[key] = value

    try:
        result = one(
            db,
            "UPDATE awards SET " + ", ".join(assignments) + " WHERE id = :id RETURNING *",
            params,
        )
        db.commit()
        return result
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(422, "Dati o riferimenti del riconoscimento non validi.") from exc


@router.delete("/awards/{award_id}", status_code=204)
def delete_award(award_id: UUID, db: Session = Depends(get_db)):
    result = db.execute(text("DELETE FROM awards WHERE id = :id"), {"id": award_id})
    if not result.rowcount:
        db.rollback()
        raise HTTPException(404, "Riconoscimento non trovato.")
    db.commit()
    return Response(status_code=204)
