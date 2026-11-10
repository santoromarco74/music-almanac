# Ricerca, calendario ed export 1.1.0

- `GET /api/v1/search?q=bowie&kind=all&limit=20`: ricerca per nome/titolo su artisti, release ed eventi. `kind`: all, artists, releases, events.
- `GET /api/v1/calendar?year=1977&month=10&day=28&event_type=RELEASE`: calendario su eventi; mese richiede anno e giorno richiede mese.
- `GET /api/v1/export/{entity}?format=json|csv&limit=5000`: entità supportate: artists, genres, releases, events, awards, editorial-items. Limite massimo 20.000 record.

Gli export sono snapshot sincroni, senza paginazione multi-file. Per dataset superiori al limite usare chiamate ripetute con filtri o implementare export asincrono in una fase successiva.
