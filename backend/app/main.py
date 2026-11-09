from fastapi import FastAPI
from sqlalchemy import text

from app.api.routes.artists import router as artists_router
from app.api.routes.genres import router as genres_router
from app.api.routes.ingestion import router as ingestion_router
from app.api.routes.memberships import router as memberships_router
from app.db import engine

app = FastAPI(
    title="Music Almanac API",
    version="0.5.0",
    description="API per l'archivio storico musicale Music Almanac.",
)
app.include_router(artists_router, prefix="/api/v1")
app.include_router(genres_router, prefix="/api/v1")
app.include_router(memberships_router, prefix="/api/v1")
app.include_router(ingestion_router, prefix="/api/v1")


@app.get("/health", tags=["system"])
def health():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}


@app.get("/api/v1", tags=["system"])
def api_root():
    return {
        "name": "Music Almanac API",
        "version": "0.5.0",
        "modules": ["artists", "genres", "memberships", "ingestion"],
    }
