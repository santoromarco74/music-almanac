# Patch Music Almanac v1.3.0

## Contenuto
- `backend/app/api/routes/musicbrainz_releases.py`: nuovo router ingestion MusicBrainz per le singole edizioni.
- `backend/app/main.py`: versione API 1.3.0 e registrazione router.
- `docs/musicbrainz-releases-1.3.0.md`: specifica funzionale e operativa.
- `tests/smoke_releases.ps1`: smoke test PowerShell.

## Installazione
1. Estrarre lo ZIP.
2. Copiare il contenuto della cartella `music_almanac_v130` nella root del repository locale `music-almanac`, mantenendo la struttura.
3. Sovrascrivere `backend/app/main.py`.
4. Ricostruire e avviare soltanto il servizio API:

```powershell
docker compose up -d --build api
```

5. Eseguire:

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/api/v1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tests\smoke_releases.ps1
```

6. Verificare `http://localhost:8000/docs`.

Non eseguire `docker compose down -v`: non è necessario e cancellerebbe i volumi persistenti del database.

## Nota
La patch non modifica lo schema SQL. I test statici non sostituiscono il collaudo runtime nel Docker locale.
