# Music Almanac — patch 0.8.1
## Correzione parametri SQL NULL

La patch corregge l'errore PostgreSQL `AmbiguousParameter` causato da filtri opzionali
scritti come `:param IS NULL` nelle query SQLAlchemy testuali.

Lo script tipizza esplicitamente i parametri opzionali nei router catalog ed events.
Non modifica lo schema PostgreSQL, non esegue migrazioni e non tocca i dati.

### Applicazione
Estrarre lo ZIP nella root del repository `music-almanac`, mantenendo la struttura,
quindi eseguire PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\fix_optional_sql_params.ps1
docker compose up -d --build api
```

Non eseguire `docker compose down -v`.

### Verifica
```powershell
curl.exe http://localhost:8000/health
curl.exe http://localhost:8000/api/v1/labels
curl.exe http://localhost:8000/api/v1/release-groups
curl.exe http://localhost:8000/api/v1/releases
curl.exe http://localhost:8000/api/v1/venues
curl.exe http://localhost:8000/api/v1/events
```

Per verificare anche i filtri:
```powershell
curl.exe "http://localhost:8000/api/v1/labels?q=columbia"
curl.exe "http://localhost:8000/api/v1/release-groups?primary_type=ALBUM"
curl.exe "http://localhost:8000/api/v1/releases?year=1972"
curl.exe "http://localhost:8000/api/v1/venues?city=London"
curl.exe "http://localhost:8000/api/v1/events?event_type=CONCERT&year=1972"
```

Se una query restituisce `[]`, significa semplicemente che non ci sono record corrispondenti;
non è un errore. Per ogni endpoint è atteso HTTP 200.
