# Charge le fichier .env à la racine du projet dans l'environnement de la session.
$racine = Split-Path -Parent $PSScriptRoot
$fichier = Join-Path $racine ".env"
if (Test-Path $fichier) {
    Get-Content $fichier -Encoding UTF8 | Where-Object { $_ -match '^\s*[^#].*=' } | ForEach-Object {
        $nom, $valeur = $_ -split '=', 2
        [Environment]::SetEnvironmentVariable($nom.Trim(), $valeur.Trim(), 'Process')
    }
}
