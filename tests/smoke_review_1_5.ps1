$ErrorActionPreference = 'Stop'
$BaseUrl = 'http://localhost:8000'
Write-Host 'Music Almanac v1.5.0 - review smoke test'

$health = Invoke-RestMethod "$BaseUrl/health"
if ($health.status -ne 'ok') { throw 'Health check fallito.' }

$api = Invoke-RestMethod "$BaseUrl/api/v1"
if ($api.version -ne '1.5.0') { throw "Versione API inattesa: $($api.version)" }
if ($api.modules -notcontains 'musicbrainz_review') { throw 'Modulo musicbrainz_review non registrato.' }

$openapi = Invoke-RestMethod "$BaseUrl/openapi.json"
$required = @(
    '/api/v1/ingestion/musicbrainz/review/queue',
    '/api/v1/ingestion/musicbrainz/review/duplicate-candidates',
    '/api/v1/ingestion/musicbrainz/review/dependencies'
)
foreach ($path in $required) {
    if ($openapi.paths.PSObject.Properties.Name -notcontains $path) {
        throw "Endpoint mancante: $path"
    }
}

$queue = Invoke-RestMethod "$BaseUrl/api/v1/ingestion/musicbrainz/review/queue?limit=5"
if (($queue.PSObject.Properties.Name -notcontains 'items') -or $queue.read_only -ne $true) { throw 'Review queue incompleta o non read-only.' }

$duplicates = Invoke-RestMethod "$BaseUrl/api/v1/ingestion/musicbrainz/review/duplicate-candidates?limit=5"
if ($duplicates.automatic_deduplication -ne $false -or $duplicates.read_only -ne $true) {
    throw 'Duplicate review deve essere read-only.'
}

$dependencies = Invoke-RestMethod "$BaseUrl/api/v1/ingestion/musicbrainz/review/dependencies?limit=5"
if ($dependencies.automatic_linking -ne $false -or $dependencies.read_only -ne $true) {
    throw 'Dependency review deve essere read-only.'
}

Write-Host ''
Write-Host 'SMOKE TEST v1.5.0 SUPERATO' -ForegroundColor Green
Write-Host 'Health, versione, modulo, 3 endpoint e risposte read-only verificati.'
