$ErrorActionPreference = 'Stop'
$workspacePath = Split-Path -Parent $PSScriptRoot
$backendPath = Join-Path $workspacePath 'backend'
$pythonPath = Join-Path $backendPath '.venv\Scripts\python.exe'
$logPath = Join-Path $workspacePath 'logs'
New-Item -ItemType Directory -Path $logPath -Force | Out-Null
$env:DB_ENGINE = 'postgresql'
$env:DB_HOST = '127.0.0.1'
$env:DB_PORT = '54329'
$env:DB_NAME = 'confectionery'
$env:DB_USER = 'confectionery'
if (-not (Test-Path Env:DB_PASSWORD)) { $env:DB_PASSWORD = '' }
$postgresPath = 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe'
$databasePath = Join-Path $workspacePath '.local-postgres'
& $postgresPath -D $databasePath status *> $null
if ($LASTEXITCODE -ne 0) {
    & $postgresPath -D $databasePath -l (Join-Path $logPath 'postgres.log') -o '-p 54329 -h 127.0.0.1' start
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL failed to start' }
}
Push-Location -LiteralPath $backendPath
try {
    & $pythonPath manage.py migrate --noinput
    if ($LASTEXITCODE -ne 0) { throw 'Migration failed' }
    & $pythonPath manage.py seed_demo
    if ($LASTEXITCODE -ne 0) { throw 'Seed failed' }
} finally { Pop-Location }
function Test-LocalPort([int]$Port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try { $client.Connect('127.0.0.1',$Port); return $true }
    catch { return $false }
    finally { $client.Dispose() }
}
$children = @()
$existingProcesses = @(Get-CimInstance Win32_Process)
if (-not (Test-LocalPort 8000)) {
    $children += Start-Process -FilePath $pythonPath -ArgumentList @('-m','config.serve','--host','127.0.0.1','--port','8000') -WorkingDirectory $backendPath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logPath 'backend.out.log') -RedirectStandardError (Join-Path $logPath 'backend.err.log') -PassThru
} else {
    $existingApi = $existingProcesses | Where-Object { $_.ExecutablePath -eq $pythonPath -and $_.CommandLine -match '\-m config\.serve\b' -and $_.CommandLine -match '\-\-port 8000\b' } | Select-Object -First 1
    if (-not $existingApi) { throw 'Port 8000 belongs to an unknown process; refusing to replace it.' }
    $children += Get-Process -Id $existingApi.ProcessId
}
$vitePath = Join-Path $workspacePath 'frontend\node_modules\vite\bin\vite.js'
if (-not (Test-LocalPort 5173)) {
    $children += Start-Process -FilePath 'C:\Program Files\nodejs\node.exe' -ArgumentList @(('"'+$vitePath+'"'),'--host','127.0.0.1','--port','5173','--strictPort') -WorkingDirectory (Join-Path $workspacePath 'frontend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logPath 'frontend.out.log') -RedirectStandardError (Join-Path $logPath 'frontend.err.log') -PassThru
} else {
    $existingUi = $existingProcesses | Where-Object { $_.Name -eq 'node.exe' -and $_.CommandLine -and $_.CommandLine.Contains('"'+$vitePath+'"') } | Select-Object -First 1
    if (-not $existingUi) { throw 'Port 5173 belongs to an unknown process; refusing to replace it.' }
    $children += Get-Process -Id $existingUi.ProcessId
}
$workerPath = Join-Path $workspacePath 'start-worker.ps1'
$existingWorker = $existingProcesses | Where-Object { $_.Name -eq 'powershell.exe' -and $_.CommandLine -and $_.CommandLine.Contains('"'+$workerPath+'"') } | Select-Object -First 1
if ($existingWorker) {
    $children += Get-Process -Id $existingWorker.ProcessId
} else {
    $children += Start-Process -FilePath 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -ArgumentList @('-NoProfile','-File',('"'+$workerPath+'"')) -WorkingDirectory $workspacePath -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logPath 'worker.out.log') -RedirectStandardError (Join-Path $logPath 'worker.err.log') -PassThru
}
@{started_at=[DateTimeOffset]::Now.ToString('o');task_name='ConfectioneryLocal';process_ids=@($children | ForEach-Object { $_.Id })} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $logPath 'local-processes.json') -Encoding UTF8
# Keep the scheduled task alive; its children survive the coding chat's lifetime.
while ($true) {
    Start-Sleep -Seconds 30
    & $postgresPath -D $databasePath status *> $null
    if ($LASTEXITCODE -ne 0) {
        & $postgresPath -D $databasePath -l (Join-Path $logPath 'postgres.log') -o '-p 54329 -h 127.0.0.1' -t 15 start
        if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL restart failed; inspect logs/postgres.log.' }
    }
    foreach ($child in $children) {
        if ($child.HasExited) { throw "Local process $($child.Id) exited with code $($child.ExitCode); inspect logs." }
    }
}
