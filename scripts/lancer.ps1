# Lance l'interface web de l'Archiviste sur http://127.0.0.1:8770 et l'ouvre dans le navigateur.
$racine = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "env.ps1")
Start-Process "http://127.0.0.1:8770"
& (Join-Path $racine ".venv\Scripts\python.exe") -m archiviste serveur --port 8770
