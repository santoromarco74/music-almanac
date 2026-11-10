from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter(tags=["provenance"])

STATUSES = {"VERIFIED", "CONFIRMED", "PRELIMINARY", "TO_VERIFY", "UNCERTAIN"}
PRECISIONS = {"YEAR", "MONTH", "DAY"}
SUBJECTS = {"ARTIST_BIRTH", "ARTIST_DEATH", "RELEASE", "EVENT"}
SUBJECT_COLUMNS = {
    "ARTIST_BIRTH": "artist_id",
    "ARTIST_DEATH": "artist_id",
    "RELEASE": "release_id",
    "EVENT": "event_id",
}


def one(db, sql, params=None):
    item = db.execute(text(sql), params or {}).mappings().first()
    return dict(item) if item else None


def many(db, sql, params=None):
    return [dict(item) for item in db.execute(text(sql), params or {}).mappings().all()]


def ensure_status(value):
    status = str(value or "TO_VERIFY").upper()
    if status not in STATUSES:
        raise HTTPException(422, "verification_status non valido.")
    return status


def validate_partial_date(year, month, day, precision):
    precision = str(precision or "").upper()
    if precision not in PRECISIONS or year is None:
        raise HTTPException(422, "Anno o precisione temporale non validi.")
    if precision == "YEAR" and (month is not None or day is not None):
        raise HTTPException(422, "La precisione YEAR richiede mese e giorno nulli.")
    if precision == "MONTH" and (month is None or day is not None):
        raise HTTPException(422, "La precisione MONTH richiede il mese e il giorno nullo.")
    if precision == "DAY":
        try:
            date(int(year), int(month), int(day))
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, "Data completa non valida.") from exc
    return precision


def validate_subject(subject_kind, artist_id, release_id, event_id):
    if subject_kind not in SUBJECTS:
        raise HTTPException(422, "subject_kind non valido.")
    expected = SUBJECT_COLUMNS[subject_kind]
    values = {"artist_id": artist_id, "release_id": release_id, "event_id": event_id}
    if values[expected] is None or sum(value is not None for value in values.values()) != 1:
        raise HTTPException(422, "Il soggetto deve contenere un solo riferimento coerente con subject_kind.")


def source_or_404(db, source_id):
    item = one(db, "SELECT * FROM sources WHERE id=:id", {"id": source_id})
    if not item:
        raise HTTPException(404, "Fonte non trovata.")
    return item


# SOURCES ---------------------------------------------------------------------

@router.get("/sources")
def list_sources(
    q: str | None = None,
    source_type: str | None = None,
    reliability_tier: int | None = Query(None, ge=1, le=5),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return many(
        db,
        """SELECT * FROM sources
        WHERE (CAST(:q AS TEXT) IS NULL OR name ILIKE '%' || :q || '%' OR publisher ILIKE '%' || :q || '%')
          AND (CAST(:t AS TEXT) IS NULL OR source_type = :t)
          AND (CAST(:r AS SMALLINT) IS NULL OR reliability_tier = :r)
        ORDER BY reliability_tier NULLS LAST, lower(name), id
        OFFSET :o LIMIT :n""",
        {"q": q, "t": source_type, "r": reliability_tier, "o": offset, "n": limit},
    )


@router.post("/sources", status_code=201)
def create_source(payload: dict, db: Session = Depends(get_db)):
    name = str(payload.get("name") or "").strip()
    source_type = str(payload.get("source_type") or "").strip().upper()
    if not name or not source_type:
        raise HTTPException(422, "name e source_type sono obbligatori.")
    tier = payload.get("reliability_tier")
    if tier is not None and not 1 <= int(tier) <= 5:
        raise HTTPException(422, "reliability_tier deve essere compreso tra 1 e 5.")
    result = one(
        db,
        """INSERT INTO sources(name,source_type,base_url,publisher,reliability_tier,license_name,terms_url,notes)
        VALUES (:name,:type,:url,:publisher,:tier,:license,:terms,:notes) RETURNING *""",
        {
            "name": name, "type": source_type, "url": payload.get("base_url"),
            "publisher": payload.get("publisher"), "tier": tier,
            "license": payload.get("license_name"), "terms": payload.get("terms_url"),
            "notes": payload.get("notes"),
        },
    )
    db.commit()
    return result


@router.get("/sources/{source_id}")
def get_source(source_id: UUID, db: Session = Depends(get_db)):
    return source_or_404(db, source_id)


@router.patch("/sources/{source_id}")
def update_source(source_id: UUID, payload: dict, db: Session = Depends(get_db)):
    old = source_or_404(db, source_id)
    allowed = {"name", "source_type", "base_url", "publisher", "reliability_tier", "license_name", "terms_url", "notes"}
    changes = {key: value for key, value in payload.items() if key in allowed}
    if not changes:
        return old
    if "name" in changes:
        changes["name"] = str(changes["name"] or "").strip()
        if not changes["name"]:
            raise HTTPException(422, "name non può essere vuoto.")
    if "source_type" in changes:
        changes["source_type"] = str(changes["source_type"] or "").strip().upper()
        if not changes["source_type"]:
            raise HTTPException(422, "source_type non può essere vuoto.")
    if changes.get("reliability_tier") is not None and not 1 <= int(changes["reliability_tier"]) <= 5:
        raise HTTPException(422, "reliability_tier deve essere compreso tra 1 e 5.")
    result = one(
        db,
        "UPDATE sources SET " + ",".join(f"{key}=:{key}" for key in changes) + " WHERE id=:id RETURNING *",
        {**changes, "id": source_id},
    )
    db.commit()
    return result


@router.delete("/sources/{source_id}", status_code=204)
def delete_source(source_id: UUID, db: Session = Depends(get_db)):
    result = db.execute(text("DELETE FROM sources WHERE id=:id"), {"id": source_id})
    if not result.rowcount:
        db.rollback()
        raise HTTPException(404, "Fonte non trovata.")
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "La fonte è referenziata da evidenze e non può essere eliminata.") from exc
    return Response(status_code=204)


# EXTERNAL IDENTIFIERS --------------------------------------------------------

@router.get("/external-identifiers")
def list_external_identifiers(
    namespace: str | None = None,
    identifier: str | None = None,
    artist_id: UUID | None = None,
    release_group_id: UUID | None = None,
    release_id: UUID | None = None,
    event_id: UUID | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return many(
        db,
        """SELECT * FROM external_identifiers
        WHERE (CAST(:ns AS TEXT) IS NULL OR namespace=:ns)
          AND (CAST(:identifier AS TEXT) IS NULL OR identifier=:identifier)
          AND (CAST(:artist AS UUID) IS NULL OR artist_id=:artist)
          AND (CAST(:group_id AS UUID) IS NULL OR release_group_id=:group_id)
          AND (CAST(:release AS UUID) IS NULL OR release_id=:release)
          AND (CAST(:event AS UUID) IS NULL OR event_id=:event)
        ORDER BY namespace,identifier,id OFFSET :o LIMIT :n""",
        {"ns": namespace.upper() if namespace else None, "identifier": identifier,
         "artist": artist_id, "group_id": release_group_id, "release": release_id,
         "event": event_id, "o": offset, "n": limit},
    )


@router.post("/external-identifiers", status_code=201)
def create_external_identifier(payload: dict, db: Session = Depends(get_db)):
    namespace = str(payload.get("namespace") or "").strip().upper()
    identifier = str(payload.get("identifier") or "").strip()
    targets = {key: payload.get(key) for key in ("artist_id", "release_group_id", "release_id", "event_id")}
    if not namespace or not identifier:
        raise HTTPException(422, "namespace e identifier sono obbligatori.")
    if sum(value is not None for value in targets.values()) != 1:
        raise HTTPException(422, "Specificare esattamente una sola entità di destinazione.")
    try:
        result = one(
            db,
            """INSERT INTO external_identifiers(namespace,identifier,artist_id,release_group_id,release_id,event_id)
            VALUES (:namespace,:identifier,:artist_id,:release_group_id,:release_id,:event_id) RETURNING *""",
            {"namespace": namespace, "identifier": identifier, **targets},
        )
        db.commit()
        return result
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Identificativo già registrato oppure entità di destinazione inesistente.") from exc


@router.get("/external-identifiers/{identifier_id}")
def get_external_identifier(identifier_id: UUID, db: Session = Depends(get_db)):
    result = one(db, "SELECT * FROM external_identifiers WHERE id=:id", {"id": identifier_id})
    if not result:
        raise HTTPException(404, "Identificativo esterno non trovato.")
    return result


@router.delete("/external-identifiers/{identifier_id}", status_code=204)
def delete_external_identifier(identifier_id: UUID, db: Session = Depends(get_db)):
    result = db.execute(text("DELETE FROM external_identifiers WHERE id=:id"), {"id": identifier_id})
    if not result.rowcount:
        db.rollback()
        raise HTTPException(404, "Identificativo esterno non trovato.")
    db.commit()
    return Response(status_code=204)


# ENTITY SOURCES --------------------------------------------------------------

@router.get("/entity-sources")
def list_entity_sources(
    source_id: UUID | None = None,
    artist_id: UUID | None = None,
    release_id: UUID | None = None,
    event_id: UUID | None = None,
    status: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return many(
        db,
        """SELECT es.*,s.name source_name,s.source_type
        FROM entity_sources es JOIN sources s ON s.id=es.source_id
        WHERE (CAST(:source AS UUID) IS NULL OR es.source_id=:source)
          AND (CAST(:artist AS UUID) IS NULL OR es.artist_id=:artist)
          AND (CAST(:release AS UUID) IS NULL OR es.release_id=:release)
          AND (CAST(:event AS UUID) IS NULL OR es.event_id=:event)
          AND (CAST(:status AS TEXT) IS NULL OR es.status=CAST(:status AS verification_status))
        ORDER BY es.retrieved_at DESC,es.id OFFSET :o LIMIT :n""",
        {"source": source_id, "artist": artist_id, "release": release_id, "event": event_id,
         "status": ensure_status(status) if status else None, "o": offset, "n": limit},
    )


@router.post("/entity-sources", status_code=201)
def create_entity_source(payload: dict, db: Session = Depends(get_db)):
    source_id = payload.get("source_id")
    if not source_id:
        raise HTTPException(422, "source_id obbligatorio.")
    targets = {key: payload.get(key) for key in ("artist_id", "release_id", "event_id")}
    if sum(value is not None for value in targets.values()) != 1:
        raise HTTPException(422, "Specificare esattamente una sola entità documentata.")
    source_or_404(db, source_id)
    try:
        result = one(
            db,
            """INSERT INTO entity_sources(source_id,artist_id,release_id,event_id,evidence_url,evidence_note,status)
            VALUES (:source_id,:artist_id,:release_id,:event_id,:url,:note,CAST(:status AS verification_status))
            RETURNING *""",
            {"source_id": source_id, **targets, "url": payload.get("evidence_url"),
             "note": payload.get("evidence_note"), "status": ensure_status(payload.get("status"))},
        )
        db.commit()
        return result
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(422, "Fonte o entità di destinazione non valida.") from exc


@router.get("/entity-sources/{link_id}")
def get_entity_source(link_id: UUID, db: Session = Depends(get_db)):
    result = one(db, "SELECT * FROM entity_sources WHERE id=:id", {"id": link_id})
    if not result:
        raise HTTPException(404, "Collegamento fonte-entità non trovato.")
    return result


@router.patch("/entity-sources/{link_id}")
def update_entity_source(link_id: UUID, payload: dict, db: Session = Depends(get_db)):
    old = get_entity_source(link_id, db)
    allowed = {"source_id", "artist_id", "release_id", "event_id", "evidence_url", "evidence_note", "status"}
    changes = {key: value for key, value in payload.items() if key in allowed}
    if not changes:
        return old
    merged = {**old, **changes}
    if sum(merged.get(key) is not None for key in ("artist_id", "release_id", "event_id")) != 1:
        raise HTTPException(422, "Il collegamento deve riferirsi a una sola entità.")
    if "source_id" in changes:
        source_or_404(db, changes["source_id"])
    if "status" in changes:
        changes["status"] = ensure_status(changes["status"])
    sets = []
    params = {"id": link_id}
    for key, value in changes.items():
        sets.append(f"{key}=CAST(:{key} AS verification_status)" if key == "status" else f"{key}=:{key}")
        params[key] = value
    try:
        result = one(db, "UPDATE entity_sources SET " + ",".join(sets) + " WHERE id=:id RETURNING *", params)
        db.commit()
        return result
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(422, "Fonte o entità di destinazione non valida.") from exc


@router.delete("/entity-sources/{link_id}", status_code=204)
def delete_entity_source(link_id: UUID, db: Session = Depends(get_db)):
    result = db.execute(text("DELETE FROM entity_sources WHERE id=:id"), {"id": link_id})
    if not result.rowcount:
        db.rollback()
        raise HTTPException(404, "Collegamento fonte-entità non trovato.")
    db.commit()
    return Response(status_code=204)


# DATE ASSERTIONS -------------------------------------------------------------

@router.get("/date-assertions/conflicts")
def date_assertion_conflicts(
    subject_kind: str | None = None,
    artist_id: UUID | None = None,
    release_id: UUID | None = None,
    event_id: UUID | None = None,
    db: Session = Depends(get_db),
):
    filters = {
        "ARTIST_BIRTH": ("artist_id", artist_id),
        "ARTIST_DEATH": ("artist_id", artist_id),
        "RELEASE": ("release_id", release_id),
        "EVENT": ("event_id", event_id),
    }
    if subject_kind and subject_kind not in SUBJECTS:
        raise HTTPException(422, "subject_kind non valido.")
    if subject_kind in {"ARTIST_BIRTH", "ARTIST_DEATH"} and artist_id is None:
        raise HTTPException(422, "artist_id obbligatorio per questo tipo di soggetto.")
    if subject_kind == "RELEASE" and release_id is None:
        raise HTTPException(422, "release_id obbligatorio.")
    if subject_kind == "EVENT" and event_id is None:
        raise HTTPException(422, "event_id obbligatorio.")

    conditions = ["1=1"]
    params = {}
    if subject_kind:
        conditions.append("subject_kind=:kind")
        params["kind"] = subject_kind
    for key, value in (("artist_id", artist_id), ("release_id", release_id), ("event_id", event_id)):
        if value is not None:
            conditions.append(f"{key}=:{key}")
            params[key] = value
    rows = many(
        db,
        """SELECT da.*,s.name source_name,s.reliability_tier
        FROM date_assertions da JOIN sources s ON s.id=da.source_id
        WHERE """ + " AND ".join(conditions) + """
        ORDER BY subject_kind,asserted_year,asserted_month NULLS FIRST,asserted_day NULLS FIRST,
                 s.reliability_tier NULLS LAST,da.retrieved_at DESC""",
        params,
    )
    # Due date parziali sono in conflitto solo se contraddicono una componente
    # temporale nota in entrambe (es. anno diverso, oppure mese diverso nello
    # stesso anno). YEAR 1972 e DAY 1972-01-01 sono compatibili.
    signatures = {
        (row["subject_kind"], row.get("artist_id"), row.get("release_id"), row.get("event_id"))
        for row in rows
    }
    output = []
    for signature in signatures:
        group = [row for row in rows if (
            row["subject_kind"], row.get("artist_id"), row.get("release_id"), row.get("event_id")
        ) == signature]
        conflicting = False
        for index, left in enumerate(group):
            for right in group[index + 1:]:
                if left["asserted_year"] != right["asserted_year"]:
                    conflicting = True
                    break
                if (left["asserted_month"] is not None and right["asserted_month"] is not None
                        and left["asserted_month"] != right["asserted_month"]):
                    conflicting = True
                    break
                if (left["asserted_day"] is not None and right["asserted_day"] is not None
                        and left["asserted_day"] != right["asserted_day"]):
                    conflicting = True
                    break
            if conflicting:
                break
        if conflicting:
            output.append({
                "subject_kind": signature[0],
                "artist_id": signature[1],
                "release_id": signature[2],
                "event_id": signature[3],
                "conflict": True,
                "assertion_count": len(group),
                "assertions": group,
            })
    return output


@router.get("/date-assertions")
def list_date_assertions(
    source_id: UUID | None = None,
    subject_kind: str | None = None,
    artist_id: UUID | None = None,
    release_id: UUID | None = None,
    event_id: UUID | None = None,
    status: str | None = None,
    year: int | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    if subject_kind and subject_kind not in SUBJECTS:
        raise HTTPException(422, "subject_kind non valido.")
    return many(
        db,
        """SELECT da.*,s.name source_name,s.source_type,s.reliability_tier
        FROM date_assertions da JOIN sources s ON s.id=da.source_id
        WHERE (CAST(:source AS UUID) IS NULL OR da.source_id=:source)
          AND (CAST(:kind AS TEXT) IS NULL OR da.subject_kind=:kind)
          AND (CAST(:artist AS UUID) IS NULL OR da.artist_id=:artist)
          AND (CAST(:release AS UUID) IS NULL OR da.release_id=:release)
          AND (CAST(:event AS UUID) IS NULL OR da.event_id=:event)
          AND (CAST(:status AS TEXT) IS NULL OR da.status=CAST(:status AS verification_status))
          AND (CAST(:year AS SMALLINT) IS NULL OR da.asserted_year=:year)
        ORDER BY da.asserted_year,da.asserted_month NULLS FIRST,da.asserted_day NULLS FIRST,da.retrieved_at DESC
        OFFSET :o LIMIT :n""",
        {"source": source_id, "kind": subject_kind, "artist": artist_id, "release": release_id,
         "event": event_id, "status": ensure_status(status) if status else None,
         "year": year, "o": offset, "n": limit},
    )


@router.post("/date-assertions", status_code=201)
def create_date_assertion(payload: dict, db: Session = Depends(get_db)):
    source_id = payload.get("source_id")
    kind = str(payload.get("subject_kind") or "").upper()
    artist_id, release_id, event_id = payload.get("artist_id"), payload.get("release_id"), payload.get("event_id")
    validate_subject(kind, artist_id, release_id, event_id)
    if not source_id:
        raise HTTPException(422, "source_id obbligatorio.")
    validate_partial_date(payload.get("asserted_year"), payload.get("asserted_month"),
                          payload.get("asserted_day"), payload.get("precision"))
    source_or_404(db, source_id)
    try:
        result = one(
            db,
            """INSERT INTO date_assertions(source_id,subject_kind,artist_id,release_id,event_id,
              asserted_year,asserted_month,asserted_day,precision,status,evidence_url,evidence_note)
            VALUES (:source,:kind,:artist,:release,:event,:year,:month,:day,
              CAST(:precision AS date_precision),CAST(:status AS verification_status),:url,:note)
            RETURNING *""",
            {"source": source_id, "kind": kind, "artist": artist_id, "release": release_id,
             "event": event_id, "year": payload.get("asserted_year"), "month": payload.get("asserted_month"),
             "day": payload.get("asserted_day"), "precision": str(payload.get("precision")).upper(),
             "status": ensure_status(payload.get("status")), "url": payload.get("evidence_url"),
             "note": payload.get("evidence_note")},
        )
        db.commit()
        return result
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(422, "Fonte, soggetto o data dell'asserzione non validi.") from exc


@router.get("/date-assertions/{assertion_id}")
def get_date_assertion(assertion_id: UUID, db: Session = Depends(get_db)):
    result = one(
        db,
        """SELECT da.*,s.name source_name,s.source_type,s.reliability_tier
        FROM date_assertions da JOIN sources s ON s.id=da.source_id WHERE da.id=:id""",
        {"id": assertion_id},
    )
    if not result:
        raise HTTPException(404, "Asserzione temporale non trovata.")
    return result


@router.patch("/date-assertions/{assertion_id}")
def update_date_assertion(assertion_id: UUID, payload: dict, db: Session = Depends(get_db)):
    old = get_date_assertion(assertion_id, db)
    allowed = {"source_id", "subject_kind", "artist_id", "release_id", "event_id",
               "asserted_year", "asserted_month", "asserted_day", "precision", "status",
               "evidence_url", "evidence_note"}
    changes = {key: value for key, value in payload.items() if key in allowed}
    if not changes:
        return old
    merged = {**old, **changes}
    validate_subject(str(merged["subject_kind"]).upper(), merged.get("artist_id"),
                     merged.get("release_id"), merged.get("event_id"))
    precision = validate_partial_date(merged.get("asserted_year"), merged.get("asserted_month"),
                                      merged.get("asserted_day"), merged.get("precision"))
    if "source_id" in changes:
        source_or_404(db, changes["source_id"])
    if "subject_kind" in changes:
        changes["subject_kind"] = str(changes["subject_kind"]).upper()
    if "precision" in changes:
        changes["precision"] = precision
    if "status" in changes:
        changes["status"] = ensure_status(changes["status"])
    sets, params = [], {"id": assertion_id}
    for key, value in changes.items():
        if key == "precision":
            sets.append("precision=CAST(:precision AS date_precision)")
        elif key == "status":
            sets.append("status=CAST(:status AS verification_status)")
        else:
            sets.append(f"{key}=:{key}")
        params[key] = value
    try:
        result = one(db, "UPDATE date_assertions SET " + ",".join(sets) + " WHERE id=:id RETURNING *", params)
        db.commit()
        return result
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(422, "Fonte, soggetto o data dell'asserzione non validi.") from exc


@router.delete("/date-assertions/{assertion_id}", status_code=204)
def delete_date_assertion(assertion_id: UUID, db: Session = Depends(get_db)):
    result = db.execute(text("DELETE FROM date_assertions WHERE id=:id"), {"id": assertion_id})
    if not result.rowcount:
        db.rollback()
        raise HTTPException(404, "Asserzione temporale non trovata.")
    db.commit()
    return Response(status_code=204)
