$ErrorActionPreference = "Stop"
$runtimeDir = Join-Path $PSScriptRoot ".dev-runtime"
$statePath = Join-Path $runtimeDir "processes.json"

if (-not (Test-Path $statePath)) {
    Write-Host "No KriyoPay development process list was found."
    exit 0
}

$state = Get-Content $statePath -Raw | ConvertFrom-Json
foreach ($record in @($state.processes)) {
    try {
        $proc = Get-Process -Id ([int]$record.processId) -ErrorAction Stop
        $started = $proc.StartTime.ToUniversalTime()
        $recorded = [DateTime]::Parse($record.startedAtUtc).ToUniversalTime()
        if ([Math]::Abs(($started - $recorded).TotalSeconds) -lt 2) {
            & taskkill.exe /PID ([string]$record.processId) /T /F | Out-Null
            Write-Host "Stopped $($record.name)."
        }
    } catch {
        Write-Host "$($record.name) is already stopped."
    }
}

Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
Write-Host "Redis was left running so queued work and container data remain available."
