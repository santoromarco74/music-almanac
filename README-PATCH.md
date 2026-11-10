# Patch Music Almanac v0.8.0

Estende le API per etichette, release groups, release, venue ed eventi. Non richiede migrazioni.

Estrarre lo ZIP nella root del progetto mantenendo i percorsi relativi e sovrascrivendo i file.

```powershell
docker compose up -d --build api
```

Smoke test:
```powershell
curl.exe http://localhost:8000/health
curl.exe http://localhost:8000/api/v1
curl.exe http://localhost:8000/api/v1/labels
curl.exe http://localhost:8000/api/v1/release-groups
curl.exe http://localhost:8000/api/v1/releases
curl.exe http://localhost:8000/api/v1/venues
curl.exe http://localhost:8000/api/v1/events
```
Non eseguire `docker compose down -v`.

## Correzione parser MusicBrainz
Dopo aver estratto il pacchetto, eseguire dalla root del progetto:
```powershell
powershell -ExecutionPolicy Bypass -File .\\scripts\\fix_musicbrainz_year_parser.ps1
```
Lo script controlla la regex della funzione `_year` nel normalizzatore v0.7.0 e corregge soltanto la variante con escaping errato. Se il parser è già corretto non modifica il file.
