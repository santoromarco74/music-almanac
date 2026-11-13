param(
    [string]$BaseUrl = "http://localhost:8000"
)

$ErrorActionPreference = "Stop"
Write-Host "Music Almanac v1.7.0 - normalization engine smoke test"

$health = Invoke-RestMethod "$BaseUrl/health"
if ($health.status -ne "ok") { throw "Health check non riuscito." }

$api = Invoke-RestMethod "$BaseUrl/api/v1"
if ($api.version -ne "1.7.0") { throw "Versione API inattesa: $($api.version)" }
if ($api.modules -notcontains "musicbrainz_normalization_engine") {
    throw "Modulo musicbrainz_normalization_engine non registrato."
}

$openapi = Invoke-RestMethod "$BaseUrl/openapi.json"
$required = @(
    "/api/v1/ingestion/musicbrainz/normalization/queue",
    "/api/v1/ingestion/musicbrainz/normalization/execute"
)
foreach ($path in $required) {
    if ($openapi.paths.PSObject.Properties.Name -notcontains $path) {
        throw "Endpoint OpenAPI mancante: $path"
    }
}

$queue = Invoke-RestMethod "$BaseUrl/api/v1/ingestion/musicbrainz/normalization/queue?limit=5"
if ($queue.read_only -ne $true) { throw "La coda deve essere read-only." }
if ($queue.normalization_performed -ne $false) { throw "La GET queue non deve normalizzare." }

Write-Host "OK: health, versione, modulo, endpoint e queue read-only."
Write-Host "Nota: il test non esegue scritture di normalizzazione."
