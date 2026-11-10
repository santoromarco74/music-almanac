$ErrorActionPreference = 'Stop'
$base = 'http://localhost:8000'
$health = Invoke-RestMethod "$base/health"
if ($health.status -ne 'ok') { throw 'Health check non superato' }
$root = Invoke-RestMethod "$base/api/v1"
if ($root.version -ne '1.1.0') { throw 'Versione API inattesa' }
Invoke-RestMethod "$base/api/v1/editorial-items?limit=1" | Out-Null
Invoke-RestMethod "$base/api/v1/editorial-tags" | Out-Null
Invoke-RestMethod "$base/api/v1/calendar?year=2000&limit=1" | Out-Null
Invoke-RestMethod "$base/api/v1/search?q=music&kind=all&limit=1" | Out-Null
Write-Host 'Smoke test superati: health, root, editorial, tags, calendar, search.'
