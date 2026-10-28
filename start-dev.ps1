param(
    [ValidateSet("Development", "Production")]
    [string] $FrontendMode = "Development",
    [ValidateRange(1024, 65525)]
    [int] $BackendPort = 8000
)

$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
$frontendDir = Join-Path $repoRoot "Frontend"
$pythonExe = Join-Path $backendDir ".venv\Scripts\python.exe"
$runtimeDir = Join-Path $repoRoot ".dev-runtime"
$logDir = Join-Path $runtimeDir "logs"
$statePath = Join-Path $runtimeDir "processes.json"

if (-not (Test-Path $pythonExe)) { throw "Backend virtual environment not found: $pythonExe" }
if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) { throw "Frontend dependencies are missing. Run 'npm ci' in the Frontend folder first." }
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Test-LocalPort([int] $port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $pending = $client.BeginConnect("127.0.0.1", $port, $null, $null)
        if (-not $pending.AsyncWaitHandle.WaitOne(800)) { return $false }
        $client.EndConnect($pending)
        return $true
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Test-DockerEngine {
    try {
        docker info --format "{{.ServerVersion}}" *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Test-KriyoPayApi([int] $port) {
    try {
        $identity = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/v1/health" -TimeoutSec 3 -ErrorAction Stop
        return $identity.service -eq "kriyopay" -and $identity.api_version -eq "v1"
    } catch { return $false }
}

$preferredBackendPort = $BackendPort
if ((Test-LocalPort $BackendPort) -and -not (Test-KriyoPayApi $BackendPort)) {
    if ($PSBoundParameters.ContainsKey("BackendPort")) {
        throw "Port $BackendPort belongs to another app or an older backend without KriyoPay's identity endpoint. Select a free port with -BackendPort."
    }
    $foundBackendPort = $false
    foreach ($candidatePort in (($preferredBackendPort + 1)..($preferredBackendPort + 10))) {
        if (-not (Test-LocalPort $candidatePort) -or (Test-KriyoPayApi $candidatePort)) {
            $BackendPort = $candidatePort
            $foundBackendPort = $true
            break
        }
    }
    if (-not $foundBackendPort) { throw "No available KriyoPay backend port was found. Select one with -BackendPort." }
    Write-Host "Port $preferredBackendPort belongs to another app; KriyoPay will use $BackendPort."
}
$env:NEXT_PUBLIC_API_URL = "http://127.0.0.1:$BackendPort/api/v1"
# Next reads env files in Frontend, not the repository-root Django .env.
$frontendEnvPath = Join-Path $frontendDir ".env.local"
$frontendEnvText = if (Test-Path -LiteralPath $frontendEnvPath) { [IO.File]::ReadAllText($frontendEnvPath) } else { "" }
$frontendApiLine = "NEXT_PUBLIC_API_URL=$($env:NEXT_PUBLIC_API_URL)"
if ($frontendEnvText -match '(?m)^NEXT_PUBLIC_API_URL=.*$') {
    $frontendEnvText = [regex]::Replace($frontendEnvText, '(?m)^NEXT_PUBLIC_API_URL=.*$', $frontendApiLine)
} else {
    $frontendEnvText = $frontendEnvText.TrimEnd() + [Environment]::NewLine + $frontendApiLine + [Environment]::NewLine
}
if (-not (Test-Path -LiteralPath $frontendEnvPath) -or [IO.File]::ReadAllText($frontendEnvPath) -ne $frontendEnvText) {
    [IO.File]::WriteAllText($frontendEnvPath, $frontendEnvText, [Text.UTF8Encoding]::new($false))
}

if (-not (Test-LocalPort 6379)) {
    $docker = Get-Command docker.exe -ErrorAction SilentlyContinue
    if (-not $docker) { throw "Redis is not listening on port 6379 and Docker CLI was not found. Start Redis locally, then run this script again." }

    if (-not (Test-DockerEngine)) {
        $desktopExe = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
        if (Test-Path $desktopExe) {
            if (-not (Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue)) {
                Start-Process -FilePath $desktopExe -WindowStyle Hidden | Out-Null
            }
            $deadline = (Get-Date).AddSeconds(60)
            while ((Get-Date) -lt $deadline -and -not (Test-DockerEngine)) { Start-Sleep -Seconds 2 }
        }
    }
    if (-not (Test-DockerEngine)) { throw "Docker Desktop is not ready. Open Docker Desktop, wait for it to start, and rerun .\start-dev.ps1." }

    $containerId = docker ps -a --filter "name=^/kriyopay-redis$" --format "{{.ID}}"
    if ($LASTEXITCODE -ne 0) { throw "Could not query Docker containers." }
    if ($containerId) {
        $running = docker inspect --format "{{.State.Running}}" kriyopay-redis
        if ($running -ne "true") {
            docker start kriyopay-redis | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Could not start the existing Redis container." }
        }
    } else {
        docker run -d --name kriyopay-redis --restart unless-stopped -p 6379:6379 -v kriyopay-redis-data:/data redis:latest redis-server --appendonly yes | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Could not start the Redis container." }
    }

    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline -and -not (Test-LocalPort 6379)) { Start-Sleep -Milliseconds 500 }
    if (-not (Test-LocalPort 6379)) { throw "Redis container started but port 6379 did not become reachable." }
}

$state = [pscustomobject]@{ processes = @() }
if (Test-Path $statePath) {
    try { $state = Get-Content $statePath -Raw | ConvertFrom-Json } catch { $state = [pscustomobject]@{ processes = @() } }
}

function Find-TrackedProcess($record) {
    try {
        $proc = Get-Process -Id ([int]$record.processId) -ErrorAction Stop
        $started = $proc.StartTime.ToUniversalTime()
        $recorded = [DateTime]::Parse($record.startedAtUtc).ToUniversalTime()
        if ([Math]::Abs(($started - $recorded).TotalSeconds) -lt 2) { return $proc }
    } catch { }
    return $null
}

function Start-DevProcess([string] $name, [string] $filePath, [string[]] $arguments, [string] $workingDirectory) {
    $old = @($state.processes | Where-Object { $_.name -eq $name }) | Select-Object -First 1
    if ($old -and (Find-TrackedProcess $old)) {
        Write-Host "$name is already running (PID $($old.processId))."
        return
    }

    $stdout = Join-Path $logDir "$name.out.log"
    $stderr = Join-Path $logDir "$name.err.log"
    $proc = Start-Process -FilePath $filePath -ArgumentList $arguments -WorkingDirectory $workingDirectory -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $state.processes = @($state.processes | Where-Object { $_.name -ne $name }) + @([pscustomobject]@{
        name = $name
        processId = $proc.Id
        startedAtUtc = $proc.StartTime.ToUniversalTime().ToString("o")
    })
    $state | ConvertTo-Json -Depth 5 | Set-Content -Path $statePath -Encoding utf8
    Write-Host "Started $name (PID $($proc.Id)); logs: $stdout"
}

if (-not (Test-LocalPort $BackendPort)) {
    $trackedDjango = @($state.processes | Where-Object { $_.name -eq "django" }) | Select-Object -First 1
    if ($trackedDjango -and (Find-TrackedProcess $trackedDjango)) {
        throw "A tracked KriyoPay backend is running on another port or is still starting. Check its logs before running start-dev.ps1 again."
    }
    Start-DevProcess "django" $pythonExe @("manage.py", "runserver", "127.0.0.1:$BackendPort") $backendDir
    $backendDeadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $backendDeadline -and -not (Test-KriyoPayApi $BackendPort)) { Start-Sleep -Milliseconds 500 }
    if (-not (Test-KriyoPayApi $BackendPort)) { throw "KriyoPay did not become ready on port $BackendPort. Check $logDir\django.err.log." }
} else {
    Write-Host "KriyoPay API identity verified on port $BackendPort."
}

$existingWorker = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -in @("python.exe", "pythonw.exe") -and $_.CommandLine -match "celery.*worker" -and $_.CommandLine -like "*$backendDir*"
} | Select-Object -First 1
if ($existingWorker) {
    Write-Host "Celery already running (PID $($existingWorker.ProcessId))."
} else {
    Start-DevProcess "celery" $pythonExe @("-m", "celery", "-A", "config", "worker", "-P", "solo", "-l", "info") $backendDir
}

$existingBeat = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -in @("python.exe", "pythonw.exe") -and $_.CommandLine -match "celery.*beat" -and $_.CommandLine -like "*$backendDir*"
} | Select-Object -First 1
if ($existingBeat) {
    Write-Host "Celery Beat already running (PID $($existingBeat.ProcessId))."
} else {
    Start-DevProcess "celery-beat" $pythonExe @("-m", "celery", "-A", "config", "beat", "-l", "info") $backendDir
}

if (-not (Test-LocalPort 3000)) {
    $npmPs1 = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npmPs1) { throw "npm was not found on PATH." }
    $npmCmd = Join-Path (Split-Path $npmPs1.Source) "npm.cmd"
    if (-not (Test-Path $npmCmd)) { $npmCmd = $npmPs1.Source }
    if ($FrontendMode -eq "Production") {
        # Use a separate build directory so development artifacts stay intact.
        $previousDist = $env:NEXT_DIST_DIR
        $previousPreview = $env:NEXT_LOCAL_PREVIEW
        try {
            $env:NEXT_DIST_DIR = ".next-preview"
            $env:NEXT_LOCAL_PREVIEW = "1"
            Push-Location -LiteralPath $frontendDir
            try {
                Write-Host "Building the client preview. This takes longer once; navigation uses precompiled pages afterwards."
                & $npmCmd run build
                if ($LASTEXITCODE -ne 0) { throw "Frontend build failed. The client preview was not started." }
            } finally { Pop-Location }
            Start-DevProcess "frontend" $npmCmd @("run", "start") $frontendDir
        } finally {
            $env:NEXT_DIST_DIR = $previousDist
            $env:NEXT_LOCAL_PREVIEW = $previousPreview
        }
    } else {
        Start-DevProcess "frontend" $npmCmd @("run", "dev") $frontendDir
    }
} else {
    Write-Host "Frontend already responds on port 3000; its current mode was kept. Stop that frontend before switching modes."
}

Write-Host "KriyoPay development services are starting."
Write-Host "Frontend: http://localhost:3000"
Write-Host "Backend:  http://localhost:$BackendPort"
Write-Host "Redis:    localhost:6379"
Write-Host "Celery Beat checks Fleet follow-ups hourly and prepares prior-month salary drafts on the first day of each month."
Write-Host "Logs:     $logDir"
Write-Host "Stop app processes with .\stop-dev.ps1 (Redis stays available)."
