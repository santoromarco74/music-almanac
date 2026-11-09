import uuid
from sqlalchemy import CHAR, CheckConstraint, Column, DateTime, ForeignKey, Numeric, SmallInteger, Table, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base

artist_genres = Table(
    "artist_genres", Base.metadata,
    Column("artist_id", UUID(as_uuid=True), ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True),
    Column("genre_id", UUID(as_uuid=True), ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
    Column("confidence", Numeric(4, 3), nullable=True),
    CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 1", name="artist_genres_confidence_check"),
)

class Artist(Base):
    __tablename__ = "artists"
    __table_args__ = (CheckConstraint("begin_year IS NULL OR end_year IS NULL OR end_year >= begin_year", name="ck_artist_years"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    sort_name: Mapped[str | None] = mapped_column(Text)
    artist_type: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PERSON'"))
    country_code: Mapped[str | None] = mapped_column(CHAR(2))
    begin_year: Mapped[int | None] = mapped_column(SmallInteger)
    end_year: Mapped[int | None] = mapped_column(SmallInteger)
    biography: Mapped[str | None] = mapped_column(Text)
    disambiguation: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    genres: Mapped[list["Genre"]] = relationship(secondary=artist_genres, back_populates="artists", lazy="selectin")
    memberships_as_group: Mapped[list["ArtistMembership"]] = relationship(foreign_keys="ArtistMembership.group_artist_id", back_populates="group_artist", cascade="all, delete-orphan")
    memberships_as_member: Mapped[list["ArtistMembership"]] = relationship(foreign_keys="ArtistMembership.member_artist_id", back_populates="member_artist", cascade="all, delete-orphan")

class Genre(Base):
    __tablename__ = "genres"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    parent_genre_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("genres.id"))
    description: Mapped[str | None] = mapped_column(Text)
    parent: Mapped["Genre | None"] = relationship(remote_side="Genre.id", back_populates="children")
    children: Mapped[list["Genre"]] = relationship(back_populates="parent")
    artists: Mapped[list[Artist]] = relationship(secondary=artist_genres, back_populates="genres")

class ArtistMembership(Base):
    __tablename__ = "artist_memberships"
    __table_args__ = (
        UniqueConstraint("group_artist_id", "member_artist_id", "role", name="uq_membership"),
        CheckConstraint("start_year IS NULL OR end_year IS NULL OR end_year >= start_year", name="ck_membership_years"),
        CheckConstraint("group_artist_id <> member_artist_id", name="ck_membership_not_self"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    group_artist_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("artists.id", ondelete="CASCADE"), nullable=False)
    member_artist_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("artists.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str | None] = mapped_column(Text)
    start_year: Mapped[int | None] = mapped_column(SmallInteger)
    end_year: Mapped[int | None] = mapped_column(SmallInteger)
    notes: Mapped[str | None] = mapped_column(Text)
    group_artist: Mapped[Artist] = relationship(foreign_keys=[group_artist_id], back_populates="memberships_as_group")
    member_artist: Mapped[Artist] = relationship(foreign_keys=[member_artist_id], back_populates="memberships_as_member")
