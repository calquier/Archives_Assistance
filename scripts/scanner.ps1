# Met l'index à jour (lecture seule). Utilisé par la tâche planifiée.
$racine = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "env.ps1")
& (Join-Path $racine ".venv\Scripts\python.exe") -m archiviste scanner
