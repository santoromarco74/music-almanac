# Music Almanac — Patch v1.2.0

Modulo di ingestion e normalizzazione dei release group MusicBrainz.

## File inclusi

- `backend/app/api/routes/musicbrainz_release_groups.py` — nuovo router.
- `backend/app/main.py` — registrazione router e versione API 1.2.0.
- `docs/musicbrainz-release-groups-1.2.0.md` — specifica, workflow e istruzioni operative.
- `tests/smoke_release_groups.ps1` — verifica rapida degli endpoint.

## Installazione

Copiare il contenuto di `backend/` e `docs/` nella root del repository mantenendo la struttura. Quindi:

```powershell
docker compose up -d --build api
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/api/v1
```

Consultare `docs/musicbrainz-release-groups-1.2.0.md` prima di eseguire i test funzionali.

**Nessuna migrazione DB.** Non usare `docker compose down -v`.

La patch è stata sottoposta a verifica sintattica Python e integrità ZIP. I test runtime devono essere eseguiti nell'ambiente Docker locale.
