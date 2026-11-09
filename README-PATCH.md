# Music Almanac — Genres API patch

Questa patch aggiunge il modulo REST per la tabella `genres`, mantenendo gli endpoint Artists esistenti.

## File inclusi

- `backend/app/schemas.py` — versione completa basata sul file locale fornito, con gli schemi GenreCreate/GenreUpdate/GenreRead.
- `backend/app/api/routes/genres.py` — CRUD dei generi.
- `backend/app/main.py` — registra il router `/api/v1/genres` e mantiene `/health`, `/api/v1` e Artists API.

## Installazione su Windows

1. Arrestare/lasciare gestire il riavvio a Docker Compose; non cancellare i volumi.
2. Estrarre lo ZIP nella root `C:\Users\saintgold\music-almanac`, mantenendo le directory e sovrascrivendo `schemas.py` e `main.py`.
3. Verificare che `backend/app/api/routes/genres.py` sia presente.
4. Eseguire:

```powershell
docker compose up --build -d
docker compose ps
docker compose logs --tail=80 api
```

5. Aprire `http://localhost:8000/docs`.

## Endpoint aggiunti

- `GET /api/v1/genres` — elenco, ricerca `q`, filtro `parent_genre_id`, `roots_only`, paginazione.
- `POST /api/v1/genres` — crea genere.
- `GET /api/v1/genres/{genre_id}` — dettaglio.
- `PATCH /api/v1/genres/{genre_id}` — modifica.
- `DELETE /api/v1/genres/{genre_id}` — elimina; restituisce 409 se ha sottogeneri.

La patch non esegue migrazioni e non modifica lo schema PostgreSQL: utilizza le colonne già presenti in `001_schema.sql`.

## Test iniziale

Creare un genere principale:

```json
{
  "name": "Rock",
  "description": "Genere di musica popolare sviluppatosi a partire dal rock and roll."
}
```

La risposta `201 Created` restituisce l'UUID assegnato al genere. Conservare quell'UUID per i test successivi e per associarlo a David Bowie tramite `PATCH /api/v1/artists/{artist_id}`.
