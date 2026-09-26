#requires -Version 5.1
<#
.SYNOPSIS
    Stop the BAYYAN dev stack.

.DESCRIPTION
    Stops the dev servers (whatever is listening on :8000 and :5173) and then
    runs `docker compose down`. After this script, nothing from the project
    is running.

.PARAMETER Volumes
    Also remove named volumes (postgres-data, minio-data). WIPES the database
    and all uploaded objects. Asks for explicit confirmation.

.EXAMPLE
    .\stop.ps1
    .\stop.ps1 -Volumes
#>
[CmdletBinding()]
param(
    [switch]$Volumes
)

Set-StrictMode -Version Latest

function Write-Step($msg)  { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host "[OK]  $msg" -ForegroundColor Green }
function Write-Info2($msg) { Write-Host "      $msg" -ForegroundColor DarkGray }

# Kill whatever owns a given TCP port. Uses taskkill /T so the whole process
# tree dies (uvicorn's --reload mode has a parent watcher and a child worker;
# killing only the listener lets the watcher respawn it).
function Stop-PortListener {
    param(
        [Parameter(Mandatory)][int]$Port,
        [Parameter(Mandatory)][string]$Label
    )
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $conn) {
        Write-Info2 "$Label not running on port $Port"
        return
    }
    # Multiple listeners on the same port shouldn't happen on Windows, but
    # iterate just in case.
    $pids = @($conn | Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($targetPid in $pids) {
        Write-Step "Stopping $Label (PID $targetPid on :$Port)"
        & taskkill /PID $targetPid /T /F 1>$null 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "$Label stopped"
        } else {
            Write-Info2 "taskkill exited $LASTEXITCODE - process may already be gone"
        }
    }
}

# Read the ports that start.ps1 actually used (may differ from 8000/5173 if the
# user passed -BackendPort / -FrontendPort). Fall back to defaults if the
# state file is missing, so stop.ps1 still cleans up after a manual run.
$stateFile = Join-Path $PSScriptRoot ".devstate.json"
$backendPort  = 8000
$frontendPort = 5173
if (Test-Path $stateFile) {
    try {
        $state = Get-Content $stateFile -Raw | ConvertFrom-Json
        if ($state.backend_port)  { $backendPort  = [int]$state.backend_port }
        if ($state.frontend_port) { $frontendPort = [int]$state.frontend_port }
    } catch {
        Write-Info2 "Could not read $stateFile - falling back to default ports."
    }
}

Stop-PortListener -Port $backendPort  -Label "Backend (uvicorn)"
Stop-PortListener -Port $frontendPort -Label "Frontend (vite)"

Push-Location $PSScriptRoot
try {
    if ($Volumes) {
        Write-Host ""
        Write-Host "This will WIPE the Postgres database AND all MinIO objects (avatars, documents)." -ForegroundColor Red
        $answer = Read-Host "Type 'wipe' to continue"
        if ($answer -ne "wipe") {
            Write-Host "Aborted." -ForegroundColor Yellow
            exit 1
        }
        Write-Step "Stopping containers and removing volumes"
        docker compose down -v
    }
    else {
        Write-Step "Stopping Postgres + MinIO"
        docker compose down
    }
}
finally {
    Pop-Location
}

if ($LASTEXITCODE -eq 0) {
    # Stale state file would mislead the next stop.ps1 invocation.
    if (Test-Path $stateFile) {
        Remove-Item $stateFile -ErrorAction SilentlyContinue
    }
    Write-Host ""
    Write-Ok "Everything stopped."
    Write-Info2 "(The Windows Terminal tabs may still be open showing 'process exited' -"
    Write-Info2 " close them manually, or press Up+Enter in each to restart that service.)"
}
