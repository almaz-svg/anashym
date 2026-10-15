param([int]$DatabasePort = 54329, [int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$env:DB_ENGINE = 'postgresql'
$env:DB_HOST = '127.0.0.1'
$env:DB_PORT = [string]$DatabasePort
$env:DB_NAME = 'confectionery'
$env:DB_USER = 'confectionery'
if (-not (Test-Path Env:DB_PASSWORD)) { $env:DB_PASSWORD = '' }
$backendPath = Join-Path $PSScriptRoot 'backend'
$pythonPath = Join-Path $backendPath '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create backend/.venv and install backend/requirements.txt first.' }
Push-Location -LiteralPath $backendPath
try {
    & $pythonPath manage.py migrate
    if ($LASTEXITCODE -ne 0) { throw 'Migration failed' }
    & $pythonPath manage.py seed_demo
    if ($LASTEXITCODE -ne 0) { throw 'Demo seed failed' }
    & $pythonPath -m config.serve --host 127.0.0.1 --port $Port
} finally { Pop-Location }
