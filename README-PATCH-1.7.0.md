# Music Almanac — Patch v1.7.0

## Contenuto

- Nuovo motore di normalizzazione MusicBrainz.
- Coda di eleggibilità read-only.
- Dry-run predefinito.
- Normalizzazione controllata di artisti, release group e release.
- Verifica delle decisioni editoriali e delle dipendenze.
- Audit append-only.
- Migrazione Alembic `0004_musicbrainz_normalization_audit`.
- Smoke test PowerShell.

## Installazione

1. Fare un commit o backup del repository locale.
2. Estrarre il contenuto mantenendo i percorsi.
3. Verificare `git diff` prima di procedere.
4. Ricostruire l'API:

```powershell
docker compose up -d --build api
```

5. Verificare la revisione corrente:

```powershell
docker compose exec api alembic current
```

6. Se la revisione corrente è `0003_musicbrainz_review_workflow`, applicare:

```powershell
docker compose exec api alembic upgrade head
```

7. Eseguire:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tests\smoke_normalization_1_7.ps1
```

Non eseguire `docker compose down -v`.

## Importante

Il primo utilizzo dell'endpoint `/execute` deve mantenere `dry_run: true`. Passare a `false` soltanto dopo aver esaminato i blocchi e verificato che la decisione editoriale sia `APPROVED`.
