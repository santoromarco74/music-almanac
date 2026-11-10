# Patch Music Almanac v0.7.0

Aggiunge:
- tabella `artist_aliases` tramite migrazione Alembic 0002;
- lookup MusicBrainz di dettaglio con `inc=aliases+tags`;
- normalizzazione di alias e tag, con associazione soltanto a generi già esistenti;
- gestione transazionale e idempotente dell'MBID;
- API version 0.7.0.

## Applicazione
Estrarre lo ZIP nella directory del progetto mantenendo i percorsi relativi e sovrascrivendo i file inclusi.

```powershell
docker compose up -d --build api
docker compose exec api alembic current
docker compose exec api alembic upgrade head
```

Se `alembic current` non mostra alcuna revisione e il database contiene già lo schema iniziale, eseguire prima:
```powershell
docker compose exec api alembic stamp 0001_existing_schema
docker compose exec api alembic upgrade head
```
Non eseguire `stamp` se una revisione è già registrata. Non usare `docker compose down -v`.

## Smoke test
```powershell
curl.exe http://localhost:8000/health
curl.exe http://localhost:8000/api/v1
```
