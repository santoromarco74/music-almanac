from fastapi import FastAPI
from sqlalchemy import text
from app.api.routes.artists import router as artists_router
from app.api.routes.genres import router as genres_router
from app.api.routes.ingestion import router as ingestion_router
from app.api.routes.memberships import router as memberships_router
from app.api.routes.musicbrainz_lookup import router as musicbrainz_lookup_router
from app.api.routes.musicbrainz_normalizer import router as musicbrainz_normalizer_router
from app.db import engine

app = FastAPI(title="Music Almanac API", version="0.7.0",
              description="API per l'archivio storico musicale Music Almanac.")
for route in (artists_router, genres_router, memberships_router, ingestion_router,
              musicbrainz_lookup_router, musicbrainz_normalizer_router):
    app.include_router(route, prefix="/api/v1")

@app.get("/health", tags=["system"])
def health():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}

@app.get("/api/v1", tags=["system"])
def api_root():
    return {"name": "Music Almanac API", "version": "0.7.0",
            "modules": ["artists","genres","memberships","ingestion",
                        "musicbrainz_lookup","musicbrainz_normalizer"]}
