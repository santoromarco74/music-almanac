# Music Almanac API v0.8.0

Nuovi endpoint:
- `GET/POST /api/v1/labels`; `GET/PATCH/DELETE /api/v1/labels/{id}`
- `GET/POST /api/v1/release-groups`; `GET/PATCH/DELETE /api/v1/release-groups/{id}`
- `GET/POST /api/v1/releases`; `GET/PATCH/DELETE /api/v1/releases/{id}`
- `GET/POST /api/v1/venues`; `GET/PATCH/DELETE /api/v1/venues/{id}`
- `GET/POST /api/v1/events`; `GET/PATCH/DELETE /api/v1/events/{id}`

Le release groups descrivono l'opera discografica concettuale; releases descrive la specifica edizione. Le associazioni artista/genere sono registrate nelle tabelle relazionali già esistenti. La precisione temporale YEAR/MONTH/DAY viene rispettata; non vengono inventati giorni per date parziali.

Nessuna migrazione DB è necessaria per questi endpoint: le tabelle sono già presenti nello schema PostgreSQL.
