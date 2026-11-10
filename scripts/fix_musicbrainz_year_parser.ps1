$ErrorActionPreference = "Stop"
$path = "backend/app/api/routes/musicbrainz_normalizer.py"
if (-not (Test-Path $path)) { throw "File non trovato: $path" }
$content = Get-Content -Raw -Encoding UTF8 $path
$wrong = 'r"^\\d{4}"'
$correct = 'r"^\d{4}"'
if ($content.Contains($wrong)) {
    $content = $content.Replace($wrong, $correct)
    Set-Content -Path $path -Value $content -Encoding UTF8 -NoNewline
    Write-Host "Parser anni corretto."
} elseif ($content.Contains($correct)) {
    Write-Host "Parser anni già corretto: nessuna modifica necessaria."
} else {
    throw "Pattern del parser non riconosciuto: verifica manualmente la funzione _year."
}
