# Patch Music Almanac v0.6.0 — Normalizzatore MusicBrainz

## File inclusi
- `backend/app/api/routes/musicbrainz_normalizer.py`
- `backend/app/main.py`
- `docs/ingestion-musicbrainz-normalizer.md`

## Applicazione
1. Estrai lo ZIP nella root del repository, sovrascrivendo `backend/app/main.py`.
2. Ricostruisci e riavvia l'API:

```powershell
docker compose up -d --build api
```

3. Verifica `http://localhost:8000/health`.
4. Consulta la preview descritta in `docs/ingestion-musicbrainz-normalizer.md`.

La patch non modifica lo schema PostgreSQL e non richiede migrazioni.
