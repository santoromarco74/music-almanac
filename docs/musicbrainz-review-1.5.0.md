# Music Almanac API 1.5.0 — MusicBrainz Review

## Obiettivo

La versione 1.5.0 introduce un livello di revisione read-only sui payload MusicBrainz già conservati in `raw_records`. Non modifica il modello relazionale e non esegue normalizzazione, collegamenti o deduplicazione automatica.

## Endpoint

### `GET /api/v1/ingestion/musicbrainz/review/queue`

Parametri:
- `status`: stato di `raw_records.processing_status`; default `PENDING`; `all` include tutti gli stati.
- `entity`: `all`, `artists`, `release_groups`, `releases`, `unknown`.
- `offset`, `limit`.

Restituisce identificativo del raw record, MBID, tipo di entità inferito, titolo/nome, hash, stato e timestamp.

### `GET /api/v1/ingestion/musicbrainz/review/duplicate-candidates`

Raggruppa i raw record MusicBrainz con lo stesso MBID e propone una revisione. `identical_payloads=true` indica hash uguali; hash differenti indicano acquisizioni con payload diversi da confrontare. Non elimina né fonde record.

### `GET /api/v1/ingestion/musicbrainz/review/dependencies`

Esamina le release in stato `PENDING` e segnala:
- release group non ancora collegato a un'entità canonica;
- artisti dei crediti non ancora collegati.

Indica l'ordine logico suggerito: release group, artisti, release. Non crea collegamenti.

## Garanzie

- Nessuna modifica a schema SQL o migrazioni Alembic.
- Nessuna scrittura su `raw_records`, `external_identifiers` o tabelle canoniche.
- Nessuna fusione o cancellazione di duplicati.
- Nessuna normalizzazione automatica.
- La dashboard esistente non viene modificata.

## Installazione

Copiare i file della patch mantenendo i percorsi relativi. Ricostruire soltanto il servizio API:

```powershell
docker compose up -d --build api
```

Non usare `docker compose down -v`.

## Test

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tests\smoke_review_1_5.ps1
```

Lo smoke test verifica health, versione, registrazione del modulo, presenza degli endpoint e proprietà read-only delle risposte. Non sostituisce i test funzionali con dati MusicBrainz reali.
