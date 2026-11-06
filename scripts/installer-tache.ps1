# Crée une tâche Windows qui met l'index à jour chaque dimanche à 20 h (lecture seule).
$script = Join-Path $PSScriptRoot "scanner.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""
$declencheur = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 20:00
Register-ScheduledTask -TaskName "Archiviste - mise a jour de l'index" -Action $action -Trigger $declencheur -Description "Indexe ESPACE PERSO et ESPACE PRO sans modifier les fichiers" -Force
Write-Host "Tâche planifiée créée."
