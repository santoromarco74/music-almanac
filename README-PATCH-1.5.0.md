# Patch Music Almanac API 1.5.0

## File inclusi

- `backend/app/api/routes/musicbrainz_review.py` — nuovi endpoint read-only di revisione.
- `backend/app/main.py` — versione 1.5.0 e registrazione del router.
- `tests/smoke_review_1_5.ps1` — smoke test.
- `docs/musicbrainz-review-1.5.0.md` — documentazione tecnica.

## Prerequisiti

La patch si basa sulla struttura API 1.4.0 del repository `main` al momento della preparazione. Prima di applicarla, assicurarsi che la versione locale contenga già i router MusicBrainz Release Groups, Releases e Pipeline introdotti nelle versioni precedenti.

## Applicazione

Estrarre l'archivio nella root del repository, sovrascrivendo `backend/app/main.py` e aggiungendo gli altri file nei rispettivi percorsi.

Ricostruire l'API:

```powershell
docker compose up -d --build api
```

Eseguire:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tests\smoke_review_1_5.ps1
```

## Impatto sul database

Nessuna migrazione. Nessuna modifica allo schema. Nessuna cancellazione o riscrittura di dati.

**Importante:** non eseguire `docker compose down -v`.
