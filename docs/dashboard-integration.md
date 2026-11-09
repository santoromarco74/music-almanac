# Integrazione dashboard

La dashboard corrente viene mantenuta come frontend separato. Il backend espone API REST versionate sotto `/api/v1`.

Endpoint previsti:
- `GET /api/v1/events?month=11&day=9&year_from=1900&year_to=2026`
- `GET /api/v1/releases?month=11&day=15&year_from=1900&year_to=2026`
- `GET /api/v1/artists/{artist_id}`
- `GET /api/v1/events/{event_id}/sources`
- `GET /api/v1/editorial-items`
- `PATCH /api/v1/editorial-items/{item_id}`

La dashboard HTML/JS esistente dovrà essere fornita o resa disponibile nel repository per un'integrazione fedele. Questo scaffold non presume che il prototipo conversazionale sia già codice sorgente riutilizzabile.
