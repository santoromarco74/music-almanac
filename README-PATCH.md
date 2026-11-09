# Music Almanac — patch MusicBrainz ingestion

Aggiunge:
- `backend/app/api/routes/ingestion.py`: connettore e endpoint di ricerca artisti.
- `backend/app/main.py`: registrazione router e versione 0.5.0.
- `.env.example`: variabile User-Agent.
- `docs/ingestion-musicbrainz.md`: istruzioni operative.

## Applicazione
Estrarre lo ZIP nella root del repository, sovrascrivendo `backend/app/main.py`. Aggiungere `MUSICBRAINZ_USER_AGENT` al `.env` locale senza sovrascrivere le credenziali esistenti.

```bash
docker compose up -d --build api
curl -X POST "http://localhost:8000/api/v1/ingestion/musicbrainz/artists/search?q=David%20Bowie&limit=5"
```

Non eseguire `docker compose down -v`: non serve alcuna migrazione e non bisogna cancellare i volumi persistenti.

La patch usa `sources`, `ingestion_runs` e `raw_records`, già presenti nello schema. I payload restano in stato `PENDING`; non vengono creati automaticamente artisti canonici. Testare nell'ambiente Docker prima di considerare validata l'integrazione.
