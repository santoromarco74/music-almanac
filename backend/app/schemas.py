from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class GenreCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent_genre_id: UUID | None = None
    description: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Il nome del genere non può essere vuoto.")
        return value


class GenreUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    parent_genre_id: UUID | None = None
    description: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Il nome del genere non può essere vuoto.")
        return value


class GenreRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    parent_genre_id: UUID | None = None
    description: str | None = None


class ArtistCreate(BaseModel):
    canonical_name: str = Field(min_length=1, max_length=500)
    sort_name: str | None = Field(default=None, max_length=500)
    artist_type: str = Field(default="PERSON", min_length=1, max_length=50)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    begin_year: int | None = Field(default=None, ge=0, le=32767)
    end_year: int | None = Field(default=None, ge=0, le=32767)
    biography: str | None = None
    disambiguation: str | None = None
    genre_ids: list[UUID] = Field(default_factory=list)

    @field_validator("canonical_name", "artist_type")
    @classmethod
    def clean_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Il campo non può essere vuoto.")
        return value

    @field_validator("country_code")
    @classmethod
    def normalize_country(cls, value: str | None) -> str | None:
        return value.upper() if value else value

    @model_validator(mode="after")
    def valid_years(self):
        if self.begin_year is not None and self.end_year is not None and self.end_year < self.begin_year:
            raise ValueError("end_year non può precedere begin_year.")
        return self


class ArtistUpdate(BaseModel):
    canonical_name: str | None = Field(default=None, min_length=1, max_length=500)
    sort_name: str | None = Field(default=None, max_length=500)
    artist_type: str | None = Field(default=None, min_length=1, max_length=50)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    begin_year: int | None = Field(default=None, ge=0, le=32767)
    end_year: int | None = Field(default=None, ge=0, le=32767)
    biography: str | None = None
    disambiguation: str | None = None
    genre_ids: list[UUID] | None = None

    @field_validator("canonical_name", "artist_type")
    @classmethod
    def clean_optional(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Il campo non può essere vuoto.")
        return value

    @field_validator("country_code")
    @classmethod
    def normalize_country(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class ArtistRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    canonical_name: str
    sort_name: str | None
    artist_type: str
    country_code: str | None
    begin_year: int | None
    end_year: int | None
    biography: str | None
    disambiguation: str | None
    created_at: datetime
    updated_at: datetime
    genres: list[GenreRead] = Field(default_factory=list)
