# Music Almanac API 1.0.0 — Awards

## Ambito del modulo

Il modulo espone CRUD per la tabella `awards` già presente nello schema PostgreSQL. Non introduce migrazioni né nuove tabelle.

Campi gestiti:

- `name` (obbligatorio)
- `awarding_body`
- `category`
- `edition_year`
- `event_id` (facoltativo, FK verso `events`)

L'eventuale `event_id` deve riferirsi a un record `events` con `event_type='AWARD'`. Se l'anno dell'edizione e quello dell'evento sono entrambi valorizzati, devono coincidere.

Lo schema attuale non modella candidature, vincitori o destinatari. Non vengono quindi introdotte API o relazioni per tali concetti. Gli artisti associati a una cerimonia restano gestiti da `event_artists` attraverso le API Events.

## Endpoint

| Metodo | Endpoint | Descrizione |
|---|---|---|
| GET | `/api/v1/awards` | Elenco con filtri e paginazione |
| POST | `/api/v1/awards` | Crea un riconoscimento/edizione |
| GET | `/api/v1/awards/{award_id}` | Dettaglio |
| PATCH | `/api/v1/awards/{award_id}` | Aggiornamento parziale |
| DELETE | `/api/v1/awards/{award_id}` | Eliminazione |

### Filtri GET

`q`, `awarding_body`, `category`, `edition_year`, `event_id`, `offset`, `limit`.

### Esempio POST

```json
{
  "name": "Grammy Awards",
  "awarding_body": "Recording Academy",
  "category": "Album of the Year",
  "edition_year": 2024,
  "event_id": null
}
```

## Installazione

Estrarre i file nella root del repository, sovrascrivendo `backend/app/main.py`, quindi eseguire:

```powershell
docker compose up -d --build api
```

Non è richiesta alcuna migrazione del database.
