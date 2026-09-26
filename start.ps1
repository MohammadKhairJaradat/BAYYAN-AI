#requires -Version 5.1
<#
.SYNOPSIS
    One-command launcher for the BAYYAN dev stack.

.DESCRIPTION
    Starts Postgres + MinIO (via docker compose), runs first-run setup if
    needed (uv sync / npm install / .env scaffolding), applies database
    migrations, then opens the backend and frontend dev servers in two
    Windows Terminal tabs. Falls back to separate PowerShell windows when
    Windows Terminal isn't installed.

.PARAMETER BackendPort
    Port for uvicorn (default 8000). Pass a different port if 8000 is taken.

.PARAMETER FrontendPort
    Port for vite (default 5173). Pass a different port if 5173 is taken.
    Vite is started with --strictPort so it fails loudly on conflict instead
    of silently shifting to 5174 (which would disagree with stop.ps1).

.PARAMETER Open
    After the stack is up, open the frontend URL in the default browser.

.EXAMPLE
    .\start.ps1
    .\start.ps1 -Open
    .\start.ps1 -BackendPort 8080
    .\start.ps1 -BackendPort 8080 -FrontendPort 4000
#>
[CmdletBinding()]
param(
    [int]$BackendPort  = 8000,
    [int]$FrontendPort = 5173,
    [switch]$Open
)

Set-StrictMode -Version Latest

# Note: we deliberately do NOT set $ErrorActionPreference = "Stop" globally.
# Windows PowerShell 5.1 wraps every line a native command writes to stderr
# into an ErrorRecord BEFORE redirection is applied (so 2>$null doesn't help),
# and Stop would then abort on harmless warnings like docker's "WARNING:
# daemon is not using the default seccomp profile". We check $LASTEXITCODE
# after each native call, and pin -ErrorAction Stop on the cmdlets that
# genuinely need abort-on-failure.

# ASCII-only output so this works under Windows PowerShell 5.1, which reads
# .ps1 files as CP1252 by default and breaks on UTF-8 glyphs.
function Write-Step($msg)  { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host "[OK]  $msg" -ForegroundColor Green }
function Write-Warn2($msg) { Write-Host "[!]   $msg" -ForegroundColor Yellow }
function Fail($msg) {
    Write-Host "[X]   $msg" -ForegroundColor Red
    exit 1
}
function ConvertTo-EncodedCommand($command) {
    [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($command))
}
function Test-LocalPort($port) {
    foreach ($hostName in @("127.0.0.1", "::1")) {
        $client = $null
        try {
            $client = New-Object System.Net.Sockets.TcpClient
            $connect = $client.BeginConnect($hostName, $port, $null, $null)
            $ready = $connect.AsyncWaitHandle.WaitOne(500)
            if (-not $ready) { continue }
            $client.EndConnect($connect)
            if ($client.Connected) { return $true }
        }
        catch {
        }
        finally {
            if ($client) { $client.Close() }
        }
    }
    return $false
}
function Wait-DevPorts($backendPort, $frontendPort, $timeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($timeoutSeconds)
    $backendReady = $false
    $frontendReady = $false

    while ((Get-Date) -lt $deadline) {
        if (-not $backendReady) { $backendReady = Test-LocalPort $backendPort }
        if (-not $frontendReady) { $frontendReady = Test-LocalPort $frontendPort }
        if ($backendReady -and $frontendReady) {
            return @{ backend = $true; frontend = $true }
        }
        Start-Sleep -Seconds 1
    }

    return @{ backend = $backendReady; frontend = $frontendReady }
}

# Sanity: are we at the repo root?
$root = $PSScriptRoot
foreach ($expected in @("docker-compose.yml", "backend", "frontend")) {
    if (-not (Test-Path (Join-Path $root $expected))) {
        Fail "Run this launcher from the project root (missing $expected)."
    }
}

# Ensure standard user tool paths (uv, nodejs, docker) are on PATH
foreach ($p in @(
    "$HOME\.local\bin",
    "C:\Program Files\nodejs",
    "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin",
    "C:\Program Files\Docker\Docker\resources\bin"
)) {
    if ((Test-Path $p) -and ($env:PATH -notlike "*$p*")) {
        $env:PATH = "$p;$env:PATH"
    }
}

# Sanity: is Docker running?
# Use 2>$null (discard) rather than 2>&1 (merge): PowerShell 5.1 wraps
# merged native stderr into ErrorRecord objects, which $ErrorActionPreference
# treats as a terminating error even when the command itself succeeded
# (e.g. the harmless "WARNING: daemon..." line docker prints to stderr).
Write-Step "Checking Docker"
docker info 1>$null 2>$null
if ($LASTEXITCODE -ne 0) {
    Fail "Docker Engine is unavailable. Open Docker Desktop; if it reports a WSL/virtualization error, enable Windows Subsystem for Linux and Virtual Machine Platform from an elevated PowerShell, reboot, then retry. See README troubleshooting."
}
Write-Ok "Docker is reachable"

$uv = Get-Command uv.exe -ErrorAction SilentlyContinue
if (-not $uv) {
    $uv = Get-Command uv -ErrorAction Stop
}
$uvExe = $uv.Source

$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npm) {
    $npm = Get-Command npm -ErrorAction Stop
}
$npmExe = $npm.Source

# Frontend deps (first run)
$frontend = Join-Path $root "frontend"
if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Write-Step "Installing frontend dependencies (first run)"
    Push-Location $frontend
    try { & $npmExe install }
    finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { Fail "npm install failed" }
    Write-Ok "Frontend dependencies installed"
} else {
    Write-Ok "Frontend dependencies already installed"
}

# Backend deps (first run)
$backend = Join-Path $root "backend"
if (-not (Test-Path (Join-Path $backend ".venv"))) {
    Write-Step "Installing backend dependencies (first run - can take a few minutes)"
    Push-Location $backend
    try { & $uvExe sync }
    finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { Fail "uv sync failed" }
    Write-Ok "Backend dependencies installed"
} else {
    Write-Ok "Backend dependencies already installed"
}

# Env file scaffolding
$backendEnv = Join-Path $backend ".env"
$backendEnvExample = Join-Path $backend ".env.example"
if (-not (Test-Path $backendEnv) -and (Test-Path $backendEnvExample)) {
    Copy-Item $backendEnvExample $backendEnv -ErrorAction Stop
    Write-Warn2 "Created backend/.env from .env.example - edit it to set a real SECRET_KEY before running in production."
}

$frontendEnv = Join-Path $frontend ".env.local"
$frontendEnvExample = Join-Path $frontend ".env.example"
if (-not (Test-Path $frontendEnv) -and (Test-Path $frontendEnvExample)) {
    Copy-Item $frontendEnvExample $frontendEnv -ErrorAction Stop
    Write-Ok "Created frontend/.env.local from .env.example"
}

# Start infrastructure (waits for healthchecks)
Write-Step "Starting Postgres + MinIO (docker compose up --wait)"
Push-Location $root
try {
    docker compose up -d --wait
    if ($LASTEXITCODE -ne 0) { Fail "docker compose up failed" }
}
finally { Pop-Location }
Write-Ok "Postgres + MinIO are healthy"

# Migrations
Write-Step "Applying database migrations"
Push-Location $backend
try {
    & $uvExe run alembic upgrade head
    if ($LASTEXITCODE -ne 0) { Fail "alembic upgrade head failed" }
}
finally { Pop-Location }
Write-Ok "Database is up to date"

# Pick a shell binary (prefer pwsh for better ANSI / Unicode)
$shellCommand = Get-Command pwsh.exe -ErrorAction SilentlyContinue
if (-not $shellCommand) {
    $shellCommand = Get-Command powershell.exe -ErrorAction Stop
}
$shellExe = $shellCommand.Source
$shellArgs = @("-NoProfile", "-NoExit")
if ((Split-Path $shellExe -Leaf) -ieq "powershell.exe") {
    $shellArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-NoExit")
}

# Persist the chosen ports so stop.ps1 knows what to kill, even if the user
# passed -BackendPort / -FrontendPort overrides.
$stateFile = Join-Path $root ".devstate.json"
@{ backend_port = $BackendPort; frontend_port = $FrontendPort } |
    ConvertTo-Json | Set-Content $stateFile -ErrorAction Stop

# Launch backend + frontend in tabs or windows.
$wt = Get-Command wt -ErrorAction SilentlyContinue
$uvExeForCommand = $uvExe.Replace("'", "''")
$npmExeForCommand = $npmExe.Replace("'", "''")
$backendCmd = @"
`$env:FRONTEND_ORIGIN = 'http://localhost:$FrontendPort'
& '$uvExeForCommand' run uvicorn app.main:app --reload --port $BackendPort
"@
$frontendCmd = @"
`$env:VITE_API_URL = 'http://localhost:$BackendPort/api/v1'
& '$npmExeForCommand' run dev -- --host 127.0.0.1 --port $FrontendPort --strictPort
"@
$backendEncoded = ConvertTo-EncodedCommand $backendCmd
$frontendEncoded = ConvertTo-EncodedCommand $frontendCmd

if ($wt) {
    Write-Step "Opening Windows Terminal tabs"
    # The inner PowerShell commands are encoded so wt.exe only sees one safe
    # argument, not separators or executable paths from the command body.
    $wtArgs = @(
        "-w", "0",
        "new-tab", "--title", "BAYYAN Backend", "--startingDirectory", $backend,
        $shellExe
    ) + $shellArgs + @(
        "-EncodedCommand", $backendEncoded,
        ";",
        "new-tab", "--title", "BAYYAN Frontend", "--startingDirectory", $frontend,
        $shellExe
    ) + $shellArgs + @(
        "-EncodedCommand", $frontendEncoded
    )
    & $wt.Source @wtArgs
    if ($LASTEXITCODE -ne 0) { Fail "Windows Terminal launch failed" }
}
else {
    Write-Step "Windows Terminal not found - opening separate PowerShell windows"
    Start-Process -FilePath $shellExe -WorkingDirectory $backend -ArgumentList ($shellArgs + @("-EncodedCommand", $backendEncoded))
    Start-Process -FilePath $shellExe -WorkingDirectory $frontend -ArgumentList ($shellArgs + @("-EncodedCommand", $frontendEncoded))
}

Write-Step "Waiting for backend and frontend ports"
$portStatus = Wait-DevPorts $BackendPort $FrontendPort 60
if (-not $portStatus.backend -or -not $portStatus.frontend) {
    if (-not $portStatus.backend) {
        Write-Warn2 "Backend did not start listening on port $BackendPort. Inspect the BAYYAN Backend tab."
    }
    if (-not $portStatus.frontend) {
        Write-Warn2 "Frontend did not start listening on port $FrontendPort. Inspect the BAYYAN Frontend tab."
    }
    Fail "Dev servers did not become ready."
}

# Summary
Write-Host ""
Write-Ok "Stack is up."
Write-Host ""
Write-Host "    Frontend   http://127.0.0.1:$FrontendPort"                       -ForegroundColor White
Write-Host "    Backend    http://localhost:$BackendPort  (docs at /docs)"       -ForegroundColor White
Write-Host "    MinIO      http://localhost:9001  (minioadmin / minioadmin)"     -ForegroundColor White
Write-Host "    Postgres   localhost:5432"                                       -ForegroundColor White
Write-Host ""
Write-Host "  Stop:  Ctrl-C each service tab, then .\stop.ps1"           -ForegroundColor DarkGray
Write-Host ""

if ($Open) {
    Start-Sleep -Seconds 2
    Start-Process "http://127.0.0.1:$FrontendPort"
}
