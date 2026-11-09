# Music Almanac — patch fase 1

Questa patch aggiunge:
- CRUD REST per le relazioni tra gruppi e membri (`/api/v1/memberships`);
- validazione degli artisti referenziati, delle date e dei duplicati;
- struttura Alembic funzionante e revisione baseline non distruttiva;
- registrazione del router memberships e versione API 0.4.0.

## Applicazione

Estrarre il contenuto dello ZIP nella radice del repository, sovrascrivendo
`backend/app/main.py` e `backend/alembic.ini` e aggiungendo gli altri file.

Ricostruire/riavviare l'API:

```bash
docker compose up -d --build
```

Per un database già creato dallo schema SQL iniziale, registrare la baseline
una sola volta:

```bash
docker compose exec api alembic stamp 0001_existing_schema
```

Non eseguire `docker compose down -v`: il volume PostgreSQL contiene i dati.

## Endpoint aggiunti

- `GET /api/v1/memberships`
- `POST /api/v1/memberships`
- `GET /api/v1/memberships/{membership_id}`
- `PATCH /api/v1/memberships/{membership_id}`
- `DELETE /api/v1/memberships/{membership_id}`

Filtri lista: `group_artist_id`, `member_artist_id`, `offset`, `limit`.

## Nota di collaudo

La patch è stata preparata sulla base dei file sorgente letti dal branch
`main`; non è stata eseguita contro il database Docker dell'utente. Prima di
considerare la fase validata occorre eseguire i test d'integrazione nel suo
ambiente. La baseline Alembic non modifica lo schema esistente.
