# Collaudo locale v1.1.0

Dopo aver applicato la patch:

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/api/v1
```

Creazione scheda:

```powershell
$body = @{ title = "Anniversario di prova"; summary = "Scheda di collaudo editoriale con un testo descrittivo sufficientemente lungo per verificare i requisiti minimi di pubblicazione."; status = "NEW" } | ConvertTo-Json
$item = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/editorial-items" -Method POST -ContentType "application/json" -Body $body
$item
```

Ricerca, calendario ed export:

```powershell
Invoke-RestMethod "http://localhost:8000/api/v1/search?q=Beatles&kind=all"
Invoke-RestMethod "http://localhost:8000/api/v1/calendar?year=1967"
Invoke-WebRequest "http://localhost:8000/api/v1/export/artists?format=csv" -OutFile artists.csv
```

Scoring:

```powershell
$score = @{ historical_importance=20; artist_relevance=15; cultural_influence=18; discographic_interest=12; source_availability=8; narrative_potential=9 } | ConvertTo-Json
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/editorial-items/$($item.id)/scores" -Method POST -ContentType "application/json" -Body $score
```

Per collaudare PUBLISHED creare prima un artista/release/evento, collegarlo alla scheda, creare una `entity_sources` per quell'entità e poi avanzare gli stati fino a IN_PROGRESS. La pubblicazione senza evidenza documentale deve restituire HTTP 422.

Non cancellare volumi Docker. I test runtime devono essere eseguiti contro il database locale: questo archivio non contiene credenziali né dati reali.
