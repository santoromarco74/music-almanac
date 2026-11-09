# MusicBrainz ingestion — Fase 1

## Endpoint
`POST /api/v1/ingestion/musicbrainz/artists/search?q=David%20Bowie&limit=10`

`q` è la frase da cercare; `limit` varia da 1 a 100 (default 10).

## Flusso
1. Individua o crea la fonte MusicBrainz in `sources`.
2. Crea un job in `ingestion_runs`.
3. Interroga l'endpoint artist di MusicBrainz in JSON.
4. Salva ogni payload originale in `raw_records`, con MBID e hash SHA-256.
5. Chiude il job come `COMPLETED` o `FAILED`.

I record restano `PENDING`: non vengono creati automaticamente record canonici in `artists`. Normalizzazione, deduplicazione semantica e revisione editoriale saranno una fase successiva.

## Configurazione e test
Impostare `MUSICBRAINZ_USER_AGENT` nel `.env` con nome applicazione, versione e contatto. Poi:

```bash
docker compose up -d --build api
curl -X POST "http://localhost:8000/api/v1/ingestion/musicbrainz/artists/search?q=David%20Bowie&limit=5"
```

Swagger: `http://localhost:8000/docs`.

Controllo DB:

```sql
SELECT id, status, records_seen, records_imported, started_at
FROM ingestion_runs ORDER BY started_at DESC LIMIT 10;

SELECT source_record_id, payload->>'name' AS artist_name, processing_status
FROM raw_records ORDER BY received_at DESC LIMIT 20;
```

## Limiti
MusicBrainz richiede un User-Agent significativo e impone al client un massimo di una richiesta al secondo. Evitare invocazioni concorrenti o cicli incontrollati. Il Web Service è gratuito per uso non commerciale; prima di un uso commerciale occorre verificare piani e condizioni applicabili. Licenza dei dati e condizioni di accesso API sono aspetti distinti.

La ricerca restituisce risultati candidati, non conferme di identità: non importare automaticamente le corrispondenze nelle tabelle canoniche.
