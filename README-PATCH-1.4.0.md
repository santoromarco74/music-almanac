# Patch Music Almanac v1.4.0

## File inclusi
- `backend/app/api/routes/musicbrainz_pipeline.py` — acquisizione batch, report run e data quality.
- `backend/app/main.py` — versione API 1.4.0 e registrazione router.
- `docs/musicbrainz-pipeline-1.4.0.md` — documentazione.
- `tests/smoke_pipeline_1_4.ps1` — smoke test PowerShell.

## Installazione
1. Estrarre lo ZIP nella root del repository, mantenendo le cartelle.
2. Verificare che `backend/app/main.py` includa già i router v1.2.0 e v1.3.0 (questa versione li mantiene).
3. Ricostruire e riavviare il servizio API:

```powershell
docker compose up -d --build api
```

Se il servizio nel compose ha un nome diverso da `api`, usare il nome effettivo del servizio. Non eseguire `docker compose down -v`.

4. Eseguire:

```powershell
.	ests\smoke_pipeline_1_4.ps1
```

## Verifiche incluse
- Health check.
- Versione API 1.4.0.
- Presenza endpoint pipeline e endpoint MusicBrainz precedenti.
- Dry-run con un MBID di esempio: non esegue chiamate esterne e non scrive dati.
- Risposta del report qualità.

Lo smoke test non esegue acquisizioni reali da MusicBrainz e non modifica dati canonici.
