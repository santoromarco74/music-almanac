$ErrorActionPreference = 'Stop'
$base = 'http://localhost:8000'

$health = Invoke-RestMethod "$base/health"
if ($health.status -ne 'ok') { throw 'Health check non valido.' }

$api = Invoke-RestMethod "$base/api/v1"
if ($api.version -ne '1.2.0') { throw "Versione API inattesa: $($api.version)" }
if ($api.modules -notcontains 'musicbrainz_release_groups') { throw 'Modulo release groups non registrato.' }

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

Write-Host 'Smoke test v1.2.0 superato: health, versione e 4 endpoint presenti.'
Write-Host 'Eseguire separatamente i test funzionali MusicBrainz descritti nella documentazione.'
