from fastapi import FastAPI
from sqlalchemy import text
from app.db import engine

app = FastAPI(
    title="Music Almanac API",
    version="0.1.0",
    description="API per l'archivio storico musicale Music Almanac.",
)

@app.get("/health")
def health():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}

@app.get("/api/v1")
def api_root():
    return {
        "name": "Music Almanac API",
        "version": "0.1.0",
        "modules": ["artists", "releases", "events", "sources", "editorial"],
    }
