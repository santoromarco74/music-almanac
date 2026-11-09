from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Artist, ArtistMembership

router = APIRouter(prefix="/memberships", tags=["artist memberships"])


class MembershipWrite(BaseModel):
    group_artist_id: UUID
    member_artist_id: UUID
    role: str | None = Field(default=None, max_length=200)
    start_year: int | None = Field(default=None, ge=0, le=32767)
    end_year: int | None = Field(default=None, ge=0, le=32767)
    notes: str | None = None

    @model_validator(mode="after")
    def validate_membership(self):
        if self.group_artist_id == self.member_artist_id:
            raise ValueError("Un artista non può appartenere a sé stesso.")
        if self.start_year is not None and self.end_year is not None and self.end_year < self.start_year:
            raise ValueError("end_year non può precedere start_year.")
        return self


class MembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    group_artist_id: UUID
    member_artist_id: UUID
    role: str | None
    start_year: int | None
    end_year: int | None
    notes: str | None


def get_membership_or_404(db: Session, membership_id: UUID) -> ArtistMembership:
    item = db.get(ArtistMembership, membership_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Relazione artista non trovata.")
    return item


def validate_artists(db: Session, group_id: UUID, member_id: UUID) -> None:
    ids = set(db.scalars(
        select(Artist.id).where(Artist.id.in_([group_id, member_id]))
    ).all())
    if group_id not in ids or member_id not in ids:
        raise HTTPException(
            status_code=422,
            detail="group_artist_id e member_artist_id devono identificare artisti esistenti.",
        )


@router.get("", response_model=list[MembershipRead])
def list_memberships(
    group_artist_id: UUID | None = None,
    member_artist_id: UUID | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    stmt = select(ArtistMembership)
    if group_artist_id is not None:
        stmt = stmt.where(ArtistMembership.group_artist_id == group_artist_id)
    if member_artist_id is not None:
        stmt = stmt.where(ArtistMembership.member_artist_id == member_artist_id)
    stmt = stmt.order_by(ArtistMembership.start_year, ArtistMembership.id).offset(offset).limit(limit)
    return list(db.scalars(stmt).all())


@router.post("", response_model=MembershipRead, status_code=status.HTTP_201_CREATED)
def create_membership(payload: MembershipWrite, db: Session = Depends(get_db)):
    validate_artists(db, payload.group_artist_id, payload.member_artist_id)
    item = ArtistMembership(**payload.model_dump())
    db.add(item)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Relazione duplicata o incompatibile con i vincoli del database.",
        )
    db.refresh(item)
    return item


@router.get("/{membership_id}", response_model=MembershipRead)
def get_membership(membership_id: UUID, db: Session = Depends(get_db)):
    return get_membership_or_404(db, membership_id)


@router.patch("/{membership_id}", response_model=MembershipRead)
def update_membership(
    membership_id: UUID,
    payload: MembershipWrite,
    db: Session = Depends(get_db),
):
    item = get_membership_or_404(db, membership_id)
    changes = payload.model_dump(exclude_unset=True)
    group_id = changes.get("group_artist_id", item.group_artist_id)
    member_id = changes.get("member_artist_id", item.member_artist_id)
    if group_id == member_id:
        raise HTTPException(status_code=422, detail="Un artista non può appartenere a sé stesso.")
    validate_artists(db, group_id, member_id)

    start_year = changes.get("start_year", item.start_year)
    end_year = changes.get("end_year", item.end_year)
    if start_year is not None and end_year is not None and end_year < start_year:
        raise HTTPException(status_code=422, detail="end_year non può precedere start_year.")

    for field, value in changes.items():
        setattr(item, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Relazione duplicata o incompatibile con i vincoli del database.",
        )
    db.refresh(item)
    return item


@router.delete("/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_membership(membership_id: UUID, db: Session = Depends(get_db)):
    item = get_membership_or_404(db, membership_id)
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
