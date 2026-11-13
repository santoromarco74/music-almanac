# Patch Music Almanac v1.6.0

Questa patch aggiunge il workflow di revisione MusicBrainz e include una correzione SQL per la Review Queue v1.5.0.

## File

- `backend/app/api/routes/musicbrainz_review_workflow.py` — decisioni, storico e linking manuale.
- `backend/migrations/versions/0003_musicbrainz_review_workflow.py` — tabella append-only per le decisioni.
- `backend/app/main.py` — versione 1.6.0 e registrazione del router aggiuntivo.
- `backend/app/api/routes/musicbrainz_review.py` — correzione del parametro SQL `status` per evitare `AmbiguousParameter`.
- `tests/smoke_review_1_6.ps1` — smoke test.
- `docs/musicbrainz-review-workflow-1.6.0.md` — documentazione.

## Applicazione

Copiare i file mantenendo i percorsi relativi. Nel file esistente `backend/app/api/routes/musicbrainz_review.py`, sostituire:

```sql
AND (:status IS NULL OR rr.processing_status=:status)
```

con:

```sql
AND (CAST(:status AS text) IS NULL OR rr.processing_status=CAST(:status AS text))
```

La sostituzione è necessaria perché il file presente nel branch GitHub `main` non contiene ancora la correzione applicata localmente durante il collaudo v1.5.0.

Poi eseguire:

```powershell
docker compose up -d --build api
docker compose exec api alembic current
docker compose exec api alembic upgrade head
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tests\smoke_review_1_6.ps1
```

Se `alembic current` non mostra `0002_artist_aliases`, non eseguire `upgrade head` prima di aver verificato lo stato della baseline e delle migrazioni già applicate. Non usare `docker compose down -v`.

## Compatibilità

- Nessuna modifica a `raw_records` o alle entità canoniche esistenti.
- Una sola nuova tabella, introdotta tramite Alembic.
- Nessuna cancellazione di payload.
- Nessun linking, deduplica o normalizzazione automatica.
- La dashboard esistente non viene modificata.
