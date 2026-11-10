$ErrorActionPreference = "Stop"
$base = "http://localhost:8000"

Write-Host "1/3 Health check..."
$health = Invoke-RestMethod "$base/health"
if ($health.status -ne "ok") { throw "Health check non superato." }
Write-Host "   OK"

Write-Host "2/3 Versione API..."
$api = Invoke-RestMethod "$base/api/v1"
if ($api.version -ne "1.3.0") { throw "Versione attesa 1.3.0, ricevuta $($api.version)." }
Write-Host "   OK - $($api.version)"

Write-Host "3/3 Endpoint MusicBrainz Releases..."
$openapi = Invoke-RestMethod "$base/openapi.json"
$required = @(
  "/api/v1/ingestion/musicbrainz/releases/search",
  "/api/v1/ingestion/musicbrainz/releases/lookup/{mbid}",
  "/api/v1/ingestion/musicbrainz/releases/preview/{mbid}",
  "/api/v1/ingestion/musicbrainz/releases/normalize/{mbid}"
)
foreach ($path in $required) {
  if ($openapi.paths.PSObject.Properties.Name -notcontains $path) {
    throw "Endpoint non registrato: $path"
  }
  Write-Host "   OK - $path"
}

Write-Host "SMOKE TEST SUPERATO"
