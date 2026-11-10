# Music Almanac API — versione 0.9.0

## Modulo Provenance

Questa versione espone le API per la gestione della provenienza documentale e delle asserzioni temporali. Non modifica lo schema PostgreSQL: utilizza le tabelle già presenti in `001_schema.sql`.

### Fonti (`sources`)

- `GET /api/v1/sources` — filtri `q`, `source_type`, `reliability_tier`, paginazione.
- `POST /api/v1/sources`
- `GET /api/v1/sources/{source_id}`
- `PATCH /api/v1/sources/{source_id}`
- `DELETE /api/v1/sources/{source_id}` — restituisce 409 se la fonte è referenziata.

Esempio:

```json
{
  "name": "MusicBrainz",
  "source_type": "DATABASE",
  "base_url": "https://musicbrainz.org",
  "publisher": "MetaBrainz Foundation",
  "reliability_tier": 2,
  "license_name": "CC BY-NC-SA",
  "terms_url": "https://musicbrainz.org/doc/About"
}
```

### Identificativi esterni (`external_identifiers`)

- `GET /api/v1/external-identifiers` — filtri per namespace, identifier e destinazione.
- `POST /api/v1/external-identifiers`
- `GET /api/v1/external-identifiers/{identifier_id}`
- `DELETE /api/v1/external-identifiers/{identifier_id}`

Il payload deve indicare esattamente una destinazione: `artist_id`, `release_group_id`, `release_id` oppure `event_id`. La coppia `namespace` + `identifier` è univoca. La patch non duplica né sostituisce la logica MusicBrainz già esistente.

### Collegamenti fonte-entità (`entity_sources`)

- `GET /api/v1/entity-sources`
- `POST /api/v1/entity-sources`
- `GET /api/v1/entity-sources/{link_id}`
- `PATCH /api/v1/entity-sources/{link_id}`
- `DELETE /api/v1/entity-sources/{link_id}`

Ogni collegamento deve riferirsi a una sola entità tra artista, release ed evento e a una fonte esistente.

### Asserzioni temporali (`date_assertions`)

- `GET /api/v1/date-assertions` — filtri per fonte, tipo soggetto, entità, stato e anno.
- `POST /api/v1/date-assertions`
- `GET /api/v1/date-assertions/{assertion_id}`
- `PATCH /api/v1/date-assertions/{assertion_id}`
- `DELETE /api/v1/date-assertions/{assertion_id}`
- `GET /api/v1/date-assertions/conflicts` — restituisce i soggetti per i quali sono registrate affermazioni temporali differenti.

`subject_kind` ammessi: `ARTIST_BIRTH`, `ARTIST_DEATH`, `RELEASE`, `EVENT`.

La precisione deve essere coerente:
- `YEAR`: anno obbligatorio, mese e giorno nulli.
- `MONTH`: anno e mese obbligatori, giorno nullo.
- `DAY`: data completa valida.

Stati ammessi: `VERIFIED`, `CONFIRMED`, `PRELIMINARY`, `TO_VERIFY`, `UNCERTAIN`.

Le asserzioni rappresentano dichiarazioni documentali provenienti da fonti specifiche. Non aggiornano automaticamente `artists`, `releases` o `events`: la scelta della data canonica resta un'attività editoriale esplicita.

## Applicazione

Estrarre lo ZIP nella root del repository e ricostruire il container API:

```powershell
docker compose up -d --build api
```

Non occorrono migrazioni. Non eseguire `docker compose down -v`.

## Test rapidi

```powershell
curl.exe http://localhost:8000/health
curl.exe http://localhost:8000/api/v1/sources
curl.exe http://localhost:8000/api/v1/external-identifiers
curl.exe http://localhost:8000/api/v1/entity-sources
curl.exe http://localhost:8000/api/v1/date-assertions
curl.exe http://localhost:8000/api/v1/date-assertions/conflicts
```

Gli endpoint GET devono restituire HTTP 200 anche quando le tabelle sono vuote.
