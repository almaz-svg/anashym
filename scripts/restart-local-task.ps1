$ErrorActionPreference = 'Stop'
$workspacePath = Split-Path -Parent $PSScriptRoot
$task = Get-ScheduledTask -TaskName 'ConfectioneryLocal'
$runnerPath = Join-Path $PSScriptRoot 'run-local.ps1'
if ($task.Actions.Arguments -notlike ('*'+$runnerPath+'*')) { throw 'Refusing to restart a task from another workspace.' }
Stop-ScheduledTask -TaskName 'ConfectioneryLocal'
$pythonPath = Join-Path $workspacePath 'backend\.venv\Scripts\python.exe'
$vitePath = Join-Path $workspacePath 'frontend\node_modules\vite\bin\vite.js'
$workerPath = Join-Path $workspacePath 'start-worker.ps1'
$processes = @(Get-CimInstance Win32_Process)
$roots = @($processes | Where-Object {
    ($_.ExecutablePath -eq $pythonPath -and $_.CommandLine -match '\-m config\.serve\b') -or
    ($_.Name -eq 'node.exe' -and $_.CommandLine -and $_.CommandLine.Contains('"'+$vitePath+'"')) -or
    ($_.Name -eq 'powershell.exe' -and $_.CommandLine -and $_.CommandLine.Contains('"'+$workerPath+'"'))
})
# Stop only validated workspace processes and their captured descendants.
function Stop-LocalTree([uint32]$ProcessId) {
    foreach ($child in @($processes | Where-Object { $_.ParentProcessId -eq $ProcessId })) {
        Stop-LocalTree $child.ProcessId
    }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}
foreach ($process in $roots) { Stop-LocalTree $process.ProcessId }
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D (Join-Path $workspacePath '.local-postgres') -m fast -t 15 stop
Start-ScheduledTask -TaskName 'ConfectioneryLocal'
$ready = $false
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    try {
        $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/ready' -TimeoutSec 2
        if ($health.status -eq 'ready') { $ready = $true; break }
    } catch { }
    Start-Sleep -Seconds 1
}
if (-not $ready) { throw 'Local task started but API is not ready; inspect logs.' }
Get-ScheduledTask -TaskName 'ConfectioneryLocal' | Select-Object TaskName,State,@{Name='API';Expression={'ready'}}
