$ErrorActionPreference = "Stop"

$targets = @(
    @{
        Path = "backend/app/api/routes/catalog.py"
        Replacements = @(
            @("(:q IS NULL OR", "(CAST(:q AS TEXT) IS NULL OR"),
            @("(:t IS NULL OR", "(CAST(:t AS TEXT) IS NULL OR"),
            @("(:y IS NULL OR", "(CAST(:y AS SMALLINT) IS NULL OR"),
            @("(:a IS NULL OR", "(CAST(:a AS UUID) IS NULL OR"),
            @("(:g IS NULL OR", "(CAST(:g AS UUID) IS NULL OR"),
            @("(:c IS NULL OR", "(CAST(:c AS CHAR(2)) IS NULL OR")
        )
    },
    @{
        Path = "backend/app/api/routes/events.py"
        Replacements = @(
            @("(:q IS NULL OR", "(CAST(:q AS TEXT) IS NULL OR"),
            @("(:city IS NULL OR", "(CAST(:city AS TEXT) IS NULL OR"),
            @("(:c IS NULL OR", "(CAST(:c AS CHAR(2)) IS NULL OR"),
            @("(:t IS NULL OR", "(CAST(:t AS TEXT) IS NULL OR"),
            @("(:y IS NULL OR", "(CAST(:y AS SMALLINT) IS NULL OR"),
            @("(:m IS NULL OR", "(CAST(:m AS SMALLINT) IS NULL OR"),
            @("(:d IS NULL OR", "(CAST(:d AS SMALLINT) IS NULL OR"),
            @("(:a IS NULL OR", "(CAST(:a AS UUID) IS NULL OR"),
            @("(:s IS NULL OR", "(CAST(:s AS TEXT) IS NULL OR")
        )
    }
)

foreach ($target in $targets) {
    if (-not (Test-Path $target.Path)) {
        throw "File non trovato: $($target.Path). Eseguire lo script dalla root del repository."
    }

    $content = Get-Content -LiteralPath $target.Path -Raw
    $changed = 0

    foreach ($replacement in $target.Replacements) {
        $old = $replacement[0]
        $new = $replacement[1]
        $count = ([regex]::Matches($content, [regex]::Escape($old))).Count
        if ($count -gt 0) {
            $content = $content.Replace($old, $new)
            $changed += $count
        }
    }

    if ($changed -eq 0) {
        Write-Host "Nessuna modifica necessaria: $($target.Path)"
    } else {
        Set-Content -LiteralPath $target.Path -Value $content -Encoding UTF8
        Write-Host "Corrette $changed condizioni SQL in $($target.Path)"
    }
}

Write-Host ""
Write-Host "Patch applicata. Ricostruire e riavviare soltanto il servizio API:"
Write-Host "docker compose up -d --build api"
