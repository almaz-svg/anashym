param([int]$DatabasePort = 54329)
$ErrorActionPreference = 'Stop'
$env:DB_ENGINE = 'postgresql'
$env:DB_HOST = '127.0.0.1'
$env:DB_PORT = [string]$DatabasePort
$env:DB_NAME = 'confectionery'
$env:DB_USER = 'confectionery'
if (-not (Test-Path Env:DB_PASSWORD)) { $env:DB_PASSWORD = '' }
$pythonPath = Join-Path $PSScriptRoot 'backend\.venv\Scripts\python.exe'
$managePath = Join-Path $PSScriptRoot 'backend\manage.py'
while ($true) {
    & $pythonPath $managePath expire_reservations
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Expiration failed; retrying in 30 seconds.' }
    & $pythonPath $managePath close_periods
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Period closing failed; retrying in 30 seconds.' }
    & $pythonPath $managePath notify_overdue
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Overdue reminders failed; retrying in 30 seconds.' }
    & $pythonPath $managePath generate_weekly_reports
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Weekly reporting failed; retrying in 30 seconds.' }
    $backupPath = Join-Path $PSScriptRoot 'scripts\daily_backup.py'
    & $pythonPath $backupPath
    if ($LASTEXITCODE -ne 0) { Write-Warning 'Daily backup failed; retrying in 30 seconds.' }
    Start-Sleep -Seconds 30
}
