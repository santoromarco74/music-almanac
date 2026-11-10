$ErrorActionPreference = "Stop"
$BaseUrl = "http://localhost:8000"
Write-Host "Music Almanac v1.4.0 - smoke test"

$health = Invoke-RestMethod "$BaseUrl/health"
if ($health.status -ne "ok") { throw "Health check fallito" }

$api = Invoke-RestMethod "$BaseUrl/api/v1"
if ($api.version -ne "1.4.0") { throw "Versione API inattesa: $($api.version)" }

$openapi = Invoke-RestMethod "$BaseUrl/openapi.json"
$required = @(
  "/api/v1/ingestion/musicbrainz/pipeline/acquire",
  "/api/v1/ingestion/musicbrainz/pipeline/runs",
  "/api/v1/ingestion/musicbrainz/pipeline/runs/{run_id}",
  "/api/v1/ingestion/musicbrainz/pipeline/quality",
  "/api/v1/ingestion/musicbrainz/releases/search",
  "/api/v1/ingestion/musicbrainz/release-groups/search"
)
foreach ($path in $required) {
  if ($openapi.paths.PSObject.Properties.Name -notcontains $path) {
    throw "Endpoint mancante: $path"
  }
}

$dryRun = @{
  artist_mbids = @("b071f9fa-14b0-4217-8e97-eb41da73f598")
  release_group_mbids = @()
  release_mbids = @()
  execute = $false
} | ConvertTo-Json -Depth 5

$plan = Invoke-RestMethod -Method Post `
  -Uri "$BaseUrl/api/v1/ingestion/musicbrainz/pipeline/acquire" `
  -ContentType "application/json" -Body $dryRun

if ($plan.mode -ne "DRY_RUN" -or $plan.items_planned -ne 1) {
  throw "Dry-run pipeline non valido"
}
if ($plan.normalization_performed -ne $false) {
  throw "Il dry-run non deve normalizzare"
}

$quality = Invoke-RestMethod "$BaseUrl/api/v1/ingestion/musicbrainz/pipeline/quality"
if ($null -eq $quality.pending_records) { throw "Quality report incompleto" }

Write-Host "SMOKE TEST SUPERATO"
