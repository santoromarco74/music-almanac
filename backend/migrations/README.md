# Alembic migrations

Il database viene inizializzato da `database/init/001_schema.sql`.
La revisione `0001_existing_schema` è una baseline vuota: non ricrea né
modifica le tabelle esistenti.

Per un database già inizializzato con lo schema bootstrap, eseguire dal
container API, una sola volta:

```bash
alembic stamp 0001_existing_schema
```

Dopo lo stamp, ogni modifica strutturale dovrà essere introdotta con una nuova
revisione incrementale Alembic. Non eseguire `docker compose down -v` su un
ambiente che contiene dati.
