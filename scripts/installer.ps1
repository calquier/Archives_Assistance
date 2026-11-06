# Installe l'Archiviste dans un environnement Python local (.venv). À lancer une fois.
$racine = Split-Path -Parent $PSScriptRoot
Set-Location $racine
if (-not (Test-Path ".venv")) { py -3 -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e ".\backend"
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env"; Write-Host "Fichier .env créé : vérifiez les dossiers indexés." }
Write-Host "Installation terminée. Lancez scripts\lancer.ps1"
