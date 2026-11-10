# MusicBrainz Artist Normalizer — v0.7.0

## Flusso
1. `POST /api/v1/ingestion/musicbrainz/artists/search?q=...`
2. `POST /api/v1/ingestion/musicbrainz/artists/lookup/{mbid}` per acquisire `aliases+tags`.
3. `GET /api/v1/ingestion/musicbrainz/artists/preview/{mbid}`.
4. `POST /api/v1/ingestion/musicbrainz/artists/normalize/{mbid}`.

## Mapping
- Nome, sort-name, tipo, paese ISO, life-span e disambiguation alimentano `artists`.
- `area` non viene convertita in paese.
- Gli alias sono salvati in `artist_aliases`, con provenienza MusicBrainz.
- I tag sono collegati solo a generi già presenti in `genres`; non vengono creati generi automaticamente.
- Il payload originale resta in `raw_records`.

## Sicurezza
- MBID già collegato: nessun nuovo artista.
- Omonimie: richiesta di scelta esplicita tramite `existing_artist_id`.
- Normalizzazione atomica in transazione.
- Gli indici univoci impediscono alias duplicati.
- Il rate limit del lookup è applicato per processo API; per deploy multi-worker servirà un limiter condiviso.

## Test PowerShell
```powershell
curl.exe -X POST "http://localhost:8000/api/v1/ingestion/musicbrainz/artists/lookup/5441c29d-3602-4898-b1a1-b77fa23b8e50"
curl.exe "http://localhost:8000/api/v1/ingestion/musicbrainz/artists/preview/5441c29d-3602-4898-b1a1-b77fa23b8e50"
```
