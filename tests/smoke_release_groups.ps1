
$ErrorActionPreference = 'Stop'
$base = "http://localhost:8000"

Write-Host "Verifica MusicBrainz Release Groups..."

# 1. Health check
$health = Invoke-RestMethod "$base/health"

if ($health.status -ne 'ok') {
    throw 'Health check non valido.'
}

# 2. API info
$api = Invoke-RestMethod "$base/api/v1"

if ($api.version -ne '1.4.0') {
    throw "Versione API inattesa: $($api.version)"
}

if ($api.modules -notcontains 'musicbrainz_release_groups') {
    throw 'Modulo release groups non registrato.'
}

# 3. OpenAPI
$openapi = Invoke-RestMethod "$base/openapi.json"

$expected = @(
    '/api/v1/ingestion/musicbrainz/release-groups/search',
    '/api/v1/ingestion/musicbrainz/release-groups/lookup/{mbid}',
    '/api/v1/ingestion/musicbrainz/release-groups/preview/{mbid}',
    '/api/v1/ingestion/musicbrainz/release-groups/normalize/{mbid}'
)

foreach ($path in $expected) {
    if ($openapi.paths.PSObject.Properties.Name -notcontains $path) {
        throw "Endpoint non registrato: $path"
    }
}

Write-Host ''
Write-Host 'SMOKE TEST RELEASE GROUPS SUPERATO' -ForegroundColor Green
Write-Host "API version: $($api.version)"
Write-Host "Health: $($health.status)"
Write-Host "Endpoint verificati: $($expected.Count)"
Write-Host 'Modulo: musicbrainz_release_groups'
Write-Host ''
Write-Host 'I test funzionali MusicBrainz devono essere eseguiti separatamente.'
