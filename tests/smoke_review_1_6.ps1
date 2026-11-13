$ErrorActionPreference = 'Stop'
$BaseUrl = 'http://localhost:8000'
$MissingId = '00000000-0000-0000-0000-000000000000'
Write-Host 'Music Almanac v1.6.0 - review workflow smoke test'

$health = Invoke-RestMethod "$BaseUrl/health"
if ($health.status -ne 'ok') { throw 'Health check fallito.' }

$api = Invoke-RestMethod "$BaseUrl/api/v1"
if ($api.version -ne '1.6.0') { throw "Versione API inattesa: $($api.version)" }
if ($api.modules -notcontains 'musicbrainz_review_workflow') { throw 'Modulo musicbrainz_review_workflow non registrato.' }

$openapi = Invoke-RestMethod "$BaseUrl/openapi.json"
$required = @(
    '/api/v1/ingestion/musicbrainz/review/queue',
    '/api/v1/ingestion/musicbrainz/review/duplicate-candidates',
    '/api/v1/ingestion/musicbrainz/review/dependencies',
    '/api/v1/ingestion/musicbrainz/review/decisions',
    '/api/v1/ingestion/musicbrainz/review/records/{raw_record_id}',
    '/api/v1/ingestion/musicbrainz/review/records/{raw_record_id}/decisions',
    '/api/v1/ingestion/musicbrainz/review/records/{raw_record_id}/decision'
)
foreach ($path in $required) {
    if ($openapi.paths.PSObject.Properties.Name -notcontains $path) {
        throw "Endpoint mancante: $path"
    }
}

$queue = Invoke-RestMethod "$BaseUrl/api/v1/ingestion/musicbrainz/review/queue?limit=5"
if (($queue.PSObject.Properties.Name -notcontains 'items') -or $queue.read_only -ne $true) { throw 'Review queue incompleta o non read-only.' }

$duplicates = Invoke-RestMethod "$BaseUrl/api/v1/ingestion/musicbrainz/review/duplicate-candidates?limit=5"
if ($duplicates.automatic_deduplication -ne $false -or $duplicates.read_only -ne $true) { throw 'Duplicate review deve essere read-only.' }

$dependencies = Invoke-RestMethod "$BaseUrl/api/v1/ingestion/musicbrainz/review/dependencies?limit=5"
if ($dependencies.automatic_linking -ne $false -or $dependencies.read_only -ne $true) { throw 'Dependency review deve essere read-only.' }

$decisions = Invoke-RestMethod "$BaseUrl/api/v1/ingestion/musicbrainz/review/decisions?limit=5"
if (($decisions.PSObject.Properties.Name -notcontains 'items') -or $decisions.read_only -ne $true) { throw 'Decision list incompleta o non read-only.' }

try {
    Invoke-RestMethod "$BaseUrl/api/v1/ingestion/musicbrainz/review/records/$MissingId"
    throw 'Il record inesistente avrebbe dovuto restituire HTTP 404.'
}
catch {
    $statusCode = [int]$_.Exception.Response.StatusCode
    if ($statusCode -ne 404) { throw }
}

try {
    Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/v1/ingestion/musicbrainz/review/records/$MissingId/decision" -ContentType 'application/json' -Body '{"action":"APPROVED"}'
    throw 'La decisione su un record inesistente avrebbe dovuto restituire HTTP 404.'
}
catch {
    $statusCode = [int]$_.Exception.Response.StatusCode
    if ($statusCode -ne 404) { throw }
}

Write-Host ''
Write-Host 'SMOKE TEST v1.6.0 SUPERATO' -ForegroundColor Green
Write-Host 'Health, versione, moduli, 7 route, GET read-only e gestione 404 verificati.'
