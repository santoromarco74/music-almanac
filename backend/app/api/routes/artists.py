from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from app.db import get_db
from app.models import Artist, Genre
from app.schemas import ArtistCreate, ArtistRead, ArtistUpdate

router = APIRouter(prefix="/artists", tags=["artists"])

def resolve_genres(db: Session, genre_ids: list[UUID]) -> list[Genre]:
    unique_ids = list(dict.fromkeys(genre_ids))
    if not unique_ids:
        return []
    genres = list(db.scalars(select(Genre).where(Genre.id.in_(unique_ids))).all())
    if len(genres) != len(unique_ids):
        raise HTTPException(status_code=422, detail="Uno o più genre_ids non corrispondono a generi esistenti.")
    by_id = {genre.id: genre for genre in genres}
    return [by_id[item] for item in unique_ids]

def get_artist_or_404(db: Session, artist_id: UUID) -> Artist:
    stmt = select(Artist).options(selectinload(Artist.genres)).where(Artist.id == artist_id)
    artist = db.scalar(stmt)
    if artist is None:
        raise HTTPException(status_code=404, detail="Artista non trovato.")
    return artist

@router.get("", response_model=list[ArtistRead])
def list_artists(
    q: str | None = Query(default=None, min_length=1, max_length=200),
    artist_type: str | None = Query(default=None, max_length=50),
    country_code: str | None = Query(default=None, min_length=2, max_length=2),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    stmt = select(Artist).options(selectinload(Artist.genres))
    if q:
        stmt = stmt.where(Artist.canonical_name.ilike(f"%{q.strip()}%"))
    if artist_type:
        stmt = stmt.where(Artist.artist_type == artist_type)
    if country_code:
        stmt = stmt.where(Artist.country_code == country_code.upper())
    stmt = stmt.order_by(func.lower(Artist.canonical_name), Artist.id).offset(offset).limit(limit)
    return list(db.scalars(stmt).all())

@router.post("", response_model=ArtistRead, status_code=status.HTTP_201_CREATED)
def create_artist(payload: ArtistCreate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude={"genre_ids"})
    artist = Artist(**data)
    artist.genres = resolve_genres(db, payload.genre_ids)
    db.add(artist)
    db.commit()
    return get_artist_or_404(db, artist.id)

@router.get("/{artist_id}", response_model=ArtistRead)
def get_artist(artist_id: UUID, db: Session = Depends(get_db)):
    return get_artist_or_404(db, artist_id)

@router.patch("/{artist_id}", response_model=ArtistRead)
def update_artist(artist_id: UUID, payload: ArtistUpdate, db: Session = Depends(get_db)):
    artist = get_artist_or_404(db, artist_id)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("canonical_name", "not-set") is None:
        raise HTTPException(status_code=422, detail="canonical_name non può essere null.")
    if changes.get("artist_type", "not-set") is None:
        raise HTTPException(status_code=422, detail="artist_type non può essere null.")
    genre_ids = changes.pop("genre_ids", None)
    for field, value in changes.items():
        setattr(artist, field, value)
    if genre_ids is not None:
        artist.genres = resolve_genres(db, genre_ids)
    db.commit()
    return get_artist_or_404(db, artist_id)

@router.delete("/{artist_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_artist(artist_id: UUID, db: Session = Depends(get_db)):
    artist = db.get(Artist, artist_id)
    if artist is None:
        raise HTTPException(status_code=404, detail="Artista non trovato.")
    db.delete(artist)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
