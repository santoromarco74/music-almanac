from fastapi import FastAPI
from sqlalchemy import text
from app.api.routes.artists import router as artists_router
from app.api.routes.awards import router as awards_router
from app.api.routes.catalog import router as catalog_router
from app.api.routes.discovery import router as discovery_router
from app.api.routes.editorial import router as editorial_router
from app.api.routes.events import router as events_router
from app.api.routes.genres import router as genres_router
from app.api.routes.ingestion import router as ingestion_router
from app.api.routes.memberships import router as memberships_router
from app.api.routes.musicbrainz_lookup import router as musicbrainz_lookup_router
from app.api.routes.musicbrainz_normalizer import router as musicbrainz_normalizer_router
from app.api.routes.musicbrainz_release_groups import router as musicbrainz_release_groups_router
from app.api.routes.musicbrainz_releases import router as musicbrainz_releases_router
from app.api.routes.musicbrainz_pipeline import router as musicbrainz_pipeline_router
from app.api.routes.musicbrainz_review import router as musicbrainz_review_router
from app.api.routes.provenance import router as provenance_router
from app.db import engine

app = FastAPI(title="Music Almanac API", version="1.5.0", description="Archivio storico musicale internazionale.")

for route in (artists_router, genres_router, memberships_router, ingestion_router,
              musicbrainz_lookup_router, musicbrainz_normalizer_router,
              musicbrainz_release_groups_router, musicbrainz_releases_router,
              musicbrainz_pipeline_router, musicbrainz_review_router, catalog_router,
              events_router, provenance_router, awards_router, editorial_router,
              discovery_router):
    app.include_router(route, prefix="/api/v1")


@app.get("/health", tags=["system"])
def health():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}


@app.get("/api/v1", tags=["system"])
def api_root():
    return {"name": "Music Almanac API", "version": "1.5.0", "modules": [
        "artists", "genres", "memberships", "ingestion", "musicbrainz_lookup",
        "musicbrainz_normalizer", "musicbrainz_release_groups", "musicbrainz_releases",
        "musicbrainz_pipeline", "musicbrainz_review", "labels", "release_groups",
        "releases", "venues", "events", "sources", "external_identifiers",
        "entity_sources", "date_assertions", "awards", "editorial", "calendar",
        "search", "export"
    ]}
