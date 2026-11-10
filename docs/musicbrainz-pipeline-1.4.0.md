# Music Almanac API — v1.4.0

## Obiettivo

La v1.4.0 introduce un coordinatore di acquisizione MusicBrainz per batch multi-entità e un report di qualità read-only. La pipeline acquisisce i payload originali, ma non esegue la normalizzazione canonica: ogni normalizzazione continua a richiedere preview e conferma esplicita tramite gli endpoint specifici già disponibili.

## Endpoint

### `POST /api/v1/ingestion/musicbrainz/pipeline/acquire`

Esempio dry-run:

```json
{
  "artist_mbids": ["b071f9fa-14b0-4217-8e97-eb41da73f598"],
  "release_group_mbids": [],
  "release_mbids": [],
  "execute": false
}
```

Il dry-run valida il piano senza chiamate esterne né scritture.

Per eseguire l'acquisizione, impostare `execute` a `true`. Limite: 50 MBID per batch. Le richieste sono serializzate e distanziate di almeno 1,05 secondi. I payload vengono conservati in `raw_records`, con SHA-256 e stato `PENDING`. Un payload identico già presente viene saltato, senza creare una seconda copia.

Stati item: `ACQUIRED`, `DUPLICATE_SKIPPED`, `NOT_FOUND`, `FAILED`. Il batch termina con stato `COMPLETED`, `PARTIAL` o `FAILED`.

### `GET /api/v1/ingestion/musicbrainz/pipeline/runs`

Elenca i batch con paginazione e filtro opzionale `status`.

### `GET /api/v1/ingestion/musicbrainz/pipeline/runs/{run_id}`

Restituisce metadati del batch e record raw associati.

### `GET /api/v1/ingestion/musicbrainz/pipeline/quality`

Report read-only con:
- record raw raggruppati per stato;
- numero di record `PENDING`;
- gruppi di hash duplicati;
- gruppi di MBID ripetuti;
- release con release group non ancora collegato;
- record con crediti artista non ancora collegati.

I conteggi sono indicatori di revisione, non istruzioni per cancellare dati. Nessuna deduplicazione automatica viene eseguita.

## Sequenza operativa consigliata

1. Preparare il batch di MBID con `execute=false`.
2. Verificare il piano e ripetere con `execute=true`.
3. Consultare il report del batch e il report globale `/quality`.
4. Eseguire la preview delle singole entità.
5. Normalizzare esplicitamente artisti e release group.
6. Normalizzare le release dopo aver risolto il collegamento al release group.
7. Ricontrollare `/quality` e mantenere i record ambigui in revisione.

## Compatibilità e persistenza

- Nessuna modifica a `001_schema.sql`.
- Nessuna migrazione Alembic.
- Nessuna modifica o cancellazione dei dati canonici.
- Nessuna eliminazione di `raw_records`.
- Gli endpoint v1.2.0 e v1.3.0 restano invariati.
- La dashboard esistente non viene ricostruita.
