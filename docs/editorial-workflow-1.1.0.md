# Editorial Workflow API 1.1.0

Base path: `/api/v1`.

## Schede
- `GET /editorial-items`: filtri `status`, `q`, `min_score`, `max_score`, `offset`, `limit`.
- `POST /editorial-items`: `title` obbligatorio; `summary`, `status`, `priority_score`, `article_url`, `notes` opzionali.
- `GET /editorial-items/{id}`: dettaglio con associazioni, tag e storico punteggi.
- `PATCH /editorial-items/{id}`: aggiorna i campi descrittivi.
- `DELETE /editorial-items/{id}`: elimina scheda e relazioni dipendenti.
- `POST /editorial-items/{id}/status`: `{ "status": "TO_VERIFY" }`.

## Stati e transizioni
`NEW → TO_VERIFY → READY → IN_PROGRESS → PUBLISHED`. Sono ammesse anche transizioni di ritorno e scarto esplicitamente definite nel codice. Una scheda non può nascere direttamente `PUBLISHED`. Per pubblicare sono necessari summary di almeno 40 caratteri, almeno un'entità collegata e almeno una fonte documentale (`entity_sources`) riferita a una delle entità collegate. La transizione a `PUBLISHED` valorizza `published_at`; le transizioni fuori da PUBLISHED lo azzerano.

## Associazioni
- `PUT /editorial-items/{id}/links/artists` con `{ "ids": ["UUID"] }`.
- `PUT /editorial-items/{id}/links/releases`.
- `PUT /editorial-items/{id}/links/events`.
Gli endpoint sostituiscono integralmente l'insieme di collegamenti del tipo indicato; `ids: []` rimuove tutti i collegamenti.

## Scoring
`POST /editorial-items/{id}/scores` accetta sei valori: historical_importance (0–25), artist_relevance (0–20), cultural_influence (0–20), discographic_interest (0–15), source_availability (0–10), narrative_potential (0–10). `total_score` viene calcolato dal server come somma, massimo 100. Ogni invio crea una nuova valutazione versionata, non sovrascrive lo storico.

## Tag
- `GET /editorial-tags`
- `POST /editorial-tags` con `{ "name": "anniversario" }`
- `PUT /editorial-items/{id}/tags` con `{ "tag_ids": ["UUID"] }` (sostituzione completa).
