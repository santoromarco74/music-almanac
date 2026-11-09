# MusicBrainz Artist Normalizer — v0.6.0

Questa patch aggiunge una normalizzazione controllata, record per record, dei payload MusicBrainz già presenti in `raw_records`.

## Endpoint

- `GET /api/v1/ingestion/musicbrainz/artists/preview/{mbid}`: mostra i campi normalizzati e gli eventuali artisti locali con lo stesso nome.
- `POST /api/v1/ingestion/musicbrainz/artists/normalize/{mbid}`: crea un artista canonico oppure collega il MBID a un artista locale esplicitamente selezionato.

Per collegare un record a un artista esistente, inviare:

```json
{"existing_artist_id": "UUID-DELL-ARTISTA"}
```

Per creare un nuovo artista, inviare `{}`. Se esiste già un artista con lo stesso nome, l'API risponde `409 Conflict` e non crea duplicati.

## Regole di mapping

- `name` → `canonical_name`
- `sort-name` → `sort_name`
- `type` → `artist_type` (`Person` → `PERSON`, `Group` → `GROUP`, ecc.)
- `life-span.begin` e `life-span.end` → anno di inizio/fine
- `disambiguation` → `disambiguation`
- `country` → `country_code`, soltanto se MusicBrainz fornisce un codice ISO a due lettere.
- `area` non viene usato come paese: ad esempio `England` è un'area/subdivision e non viene trasformata automaticamente in `GB`.

Alias e tag non vengono ancora importati in tabelle canoniche: il payload integrale rimane conservato in `raw_records`. La precisione delle date originali resta quindi disponibile anche se `artists` memorizza soltanto l'anno.

## Idempotenza e sicurezza

- L'identificativo esterno usa `namespace = MUSICBRAINZ_ARTIST` e il MBID come `identifier`.
- Un MBID già collegato non genera un secondo artista.
- Le corrispondenze per nome non vengono collegate automaticamente: serve una scelta esplicita.
- Il record grezzo passa a `PROCESSED` soltanto dopo il commit.
- La normalizzazione opera su un singolo MBID; non esiste importazione massiva automatica.

## Test manuale

```powershell
curl.exe "http://localhost:8000/api/v1/ingestion/musicbrainz/artists/preview/5441c29d-3602-4898-b1a1-b77fa23b8e50"
```

David Bowie esiste già nel database locale. La preview dovrebbe quindi mostrare una corrispondenza locale. Per associare il MBID al record esistente, usare il suo UUID:

```powershell
curl.exe -X POST "http://localhost:8000/api/v1/ingestion/musicbrainz/artists/normalize/5441c29d-3602-4898-b1a1-b77fa23b8e50" -H "Content-Type: application/json" -d "{`"existing_artist_id`":`"9523bae9-e348-4e64-aac7-76a57683a399`"}"
```

Non eseguire `docker compose down -v`: eliminerebbe i volumi persistenti del database.
