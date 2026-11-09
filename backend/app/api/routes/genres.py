from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Genre
from app.schemas import GenreCreate, GenreRead, GenreUpdate


router = APIRouter(prefix="/genres", tags=["genres"])


def get_genre_or_404(db: Session, genre_id: UUID) -> Genre:
    genre = db.get(Genre, genre_id)
    if genre is None:
        raise HTTPException(status_code=404, detail="Genere non trovato.")
    return genre


def validate_parent(db: Session, parent_id: UUID | None, current_id: UUID | None = None) -> None:
    if parent_id is None:
        return
    if current_id is not None and parent_id == current_id:
        raise HTTPException(status_code=422, detail="Un genere non può essere il proprio genitore.")

    parent = db.get(Genre, parent_id)
    if parent is None:
        raise HTTPException(status_code=422, detail="parent_genre_id non corrisponde a un genere esistente.")

    # Impedisce cicli nella gerarchia (es. Rock -> Alternative -> Rock).
    visited: set[UUID] = set()
    cursor = parent
    while cursor is not None:
        if current_id is not None and cursor.id == current_id:
            raise HTTPException(status_code=422, detail="La modifica creerebbe un ciclo nella gerarchia dei generi.")
        if cursor.id in visited:
            raise HTTPException(status_code=409, detail="La gerarchia dei generi contiene già un ciclo.")
        visited.add(cursor.id)
        cursor = db.get(Genre, cursor.parent_genre_id) if cursor.parent_genre_id else None


@router.get("", response_model=list[GenreRead])
def list_genres(
    q: str | None = Query(default=None, min_length=1, max_length=200),
    parent_genre_id: UUID | None = Query(default=None),
    roots_only: bool = Query(default=False),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    stmt = select(Genre)
    if q:
        stmt = stmt.where(Genre.name.ilike(f"%{q.strip()}%"))
    if roots_only:
        stmt = stmt.where(Genre.parent_genre_id.is_(None))
    elif parent_genre_id is not None:
        stmt = stmt.where(Genre.parent_genre_id == parent_genre_id)
    stmt = stmt.order_by(func.lower(Genre.name), Genre.id).offset(offset).limit(limit)
    return list(db.scalars(stmt).all())


@router.post("", response_model=GenreRead, status_code=status.HTTP_201_CREATED)
def create_genre(payload: GenreCreate, db: Session = Depends(get_db)):
    validate_parent(db, payload.parent_genre_id)
    genre = Genre(
        name=payload.name,
        parent_genre_id=payload.parent_genre_id,
        description=payload.description,
    )
    db.add(genre)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Esiste già un genere con questo nome.")
    db.refresh(genre)
    return genre


@router.get("/{genre_id}", response_model=GenreRead)
def get_genre(genre_id: UUID, db: Session = Depends(get_db)):
    return get_genre_or_404(db, genre_id)


@router.patch("/{genre_id}", response_model=GenreRead)
def update_genre(genre_id: UUID, payload: GenreUpdate, db: Session = Depends(get_db)):
    genre = get_genre_or_404(db, genre_id)
    changes = payload.model_dump(exclude_unset=True)

    if "name" in changes and changes["name"] is None:
        raise HTTPException(status_code=422, detail="name non può essere null.")

    if "parent_genre_id" in changes:
        validate_parent(db, changes["parent_genre_id"], current_id=genre.id)

    for field, value in changes.items():
        setattr(genre, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Esiste già un genere con questo nome.")

    db.refresh(genre)
    return genre


@router.delete("/{genre_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_genre(genre_id: UUID, db: Session = Depends(get_db)):
    genre = get_genre_or_404(db, genre_id)

    has_children = db.scalar(
        select(Genre.id).where(Genre.parent_genre_id == genre_id).limit(1)
    )
    if has_children is not None:
        raise HTTPException(
            status_code=409,
            detail="Impossibile eliminare il genere: contiene sottogeneri. Riassegnarli o eliminarli prima.",
        )

    db.delete(genre)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Il genere è ancora referenziato e non può essere eliminato.")

    return Response(status_code=status.HTTP_204_NO_CONTENT)
