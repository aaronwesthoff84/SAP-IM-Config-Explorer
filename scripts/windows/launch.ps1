<#
.SYNOPSIS
    Starts the SAP IM Config Explorer web application on Windows.

.DESCRIPTION
    Launches the application server bound to loopback (127.0.0.1) by default.
    Ensures the Python environment is ready, checks offline vendored dependencies,
    creates the local user data directory structure, monitors startup health,
    and opens the user's default browser.

.PARAMETER Port
    TCP port to bind the server to (default: 8000).

.PARAMETER HostAddress
    Network interface to bind to (default: "127.0.0.1" - loopback only).

.PARAMETER DataDir
    Path to user data directory for exports and sessions.
    Default: %LOCALAPPDATA%\SAP-IM-Config-Explorer.

.PARAMETER Headless
    If specified, runs without opening the default web browser.

.PARAMETER Background
    If specified, launches the server process in the background and writes PID to .runtime\app.pid.

.EXAMPLE
    .\launch.ps1
    .\launch.ps1 -Port 8080 -Background
    .\launch.ps1 -Headless
#>

[CmdletBinding()]
param(
    [int]$Port = 8000,
    [string]$HostAddress = "127.0.0.1",
    [string]$DataDir = "$env:LOCALAPPDATA\SAP-IM-Config-Explorer",
    [switch]$Headless,
    [switch]$Background
)

$ErrorActionPreference = "Stop"

# Determine project root directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Resolve-Path "$ScriptDir\..\.." -ErrorAction SilentlyContinue
if (-not $ProjectRoot -or -not (Test-Path "$ProjectRoot\sap_im_config_graph_explorer")) {
    $ProjectRoot = Resolve-Path "$ScriptDir\.." -ErrorAction SilentlyContinue
}
if (-not $ProjectRoot -or -not (Test-Path "$ProjectRoot\sap_im_config_graph_explorer")) {
    $ProjectRoot = Resolve-Path "$ScriptDir"
}
$ProjectRoot = $ProjectRoot.Path

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " SAP IM Config Explorer - Windows Offline Launcher" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Project Root: $ProjectRoot"

# 1. Initialize User Data Directory
Write-Host "[1/5] Initializing local user data directory..." -ForegroundColor Green
$SessionsDir = Join-Path $DataDir "sessions"
$ExportsDir = Join-Path $DataDir "exports"
$WaiversDir = Join-Path $DataDir "waivers"
$LogsDir = Join-Path $DataDir "logs"
$RuntimeDir = Join-Path $ProjectRoot ".runtime"

New-Item -ItemType Directory -Force -Path $SessionsDir, $ExportsDir, $WaiversDir, $LogsDir, $RuntimeDir | Out-Null
$env:SAP_IM_DATA_DIR = $DataDir
Write-Host "  Data Directory: $DataDir"
Write-Host "  Logs: $LogsDir\server.log"

# 2. Locate Python Runtime
Write-Host "[2/5] Locating Python environment..." -ForegroundColor Green
$PythonExe = $null

if (Test-Path "$ProjectRoot\.venv\Scripts\python.exe") {
    $PythonExe = "$ProjectRoot\.venv\Scripts\python.exe"
    Write-Host "  Using virtual environment: $PythonExe"
} elseif (Test-Path "$ProjectRoot\python\python.exe") {
    $PythonExe = "$ProjectRoot\python\python.exe"
    Write-Host "  Using embedded Python: $PythonExe"
} else {
    $SystemPython = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($SystemPython) {
        $PythonExe = $SystemPython.Source
        Write-Host "  Using system Python: $PythonExe"
    }
}

if (-not $PythonExe) {
    Write-Error "Python 3.10+ was not found on your system or in .venv. Please install Python or unpack the full offline distribution bundle."
    exit 1
}

# 3. Check / Install Offline Dependencies
Write-Host "[3/5] Verifying runtime dependencies..." -ForegroundColor Green
$WheelsDir = Join-Path $ProjectRoot "wheels"
$ReqFile = Join-Path $ProjectRoot "requirements.txt"

# Test if uvicorn and fastapi are importable
$ImportResult = & $PythonExe -c "import fastapi, uvicorn, defusedxml; print('OK')" 2>$null

if ($ImportResult -ne "OK") {
    if (Test-Path $WheelsDir -and (Test-Path $ReqFile)) {
        Write-Host "  Installing dependencies from offline wheels cache..." -ForegroundColor Yellow
        & $PythonExe -m pip install --no-index --find-links "$WheelsDir" -r "$ReqFile"
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to install dependencies from offline wheels cache."
            exit 1
        }
    } else {
        Write-Host "  Dependencies not pre-installed. Attempting local package check..." -ForegroundColor Yellow
    }
} else {
    Write-Host "  All required runtime modules are present." -ForegroundColor Green
}

# 4. Check Port & Loopback Binding
Write-Host "[4/5] Checking network binding..." -ForegroundColor Green
if ($HostAddress -ne "127.0.0.1" -and $HostAddress -ne "localhost") {
    Write-Host "  WARNING: HostAddress '$HostAddress' is not loopback. Standard policy is 127.0.0.1 for local-first offline isolation." -ForegroundColor Yellow
} else {
    Write-Host "  Bound to secure local loopback: ${HostAddress}:${Port}"
}

$PidFile = Join-Path $RuntimeDir "app.pid"
if (Test-Path $PidFile) {
    $ExistingPid = (Get-Content $PidFile -ErrorAction SilentlyContinue).Trim()
    if ($ExistingPid -and (Get-Process -Id $ExistingPid -ErrorAction SilentlyContinue)) {
        Write-Host "  Server is already running with PID $ExistingPid." -ForegroundColor Yellow
        $HealthUrl = "http://${HostAddress}:${Port}/health"
        try {
            $Response = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 3 -ErrorAction Stop
            if ($Response.status -eq "ok") {
                Write-Host "  Server is healthy and responsive at $HealthUrl." -ForegroundColor Green
                if (-not $Headless) {
                    Start-Process "http://${HostAddress}:${Port}"
                }
                exit 0
            }
        } catch {}
    }
}

# 5. Launch Server Process
Write-Host "[5/5] Launching SAP IM Config Explorer server..." -ForegroundColor Green
$ServerLog = Join-Path $LogsDir "server.log"

$UvicornArgs = @(
    "-m", "uvicorn",
    "sap_im_config_graph_explorer.app:app",
    "--host", $HostAddress,
    "--port", $Port.ToString()
)

$ServerUrl = "http://${HostAddress}:${Port}"

if ($Background) {
    $StartProcessArgs = @{
        FilePath = $PythonExe
        ArgumentList = $UvicornArgs
        WorkingDirectory = $ProjectRoot
        RedirectStandardOutput = $ServerLog
        RedirectStandardError = $ServerLog
        WindowStyle = "Hidden"
        PassThru = $true
    }
    $Process = Start-Process @StartProcessArgs
    $Process.Id | Out-File -FilePath $PidFile -Encoding utf8 -Force
    Write-Host "  Server process started in background (PID: $($Process.Id))."
    Write-Host "  PID recorded to: $PidFile"
} else {
    # If foreground, start in a separate job or background thread so we can verify health and open browser
    $StartProcessArgs = @{
        FilePath = $PythonExe
        ArgumentList = $UvicornArgs
        WorkingDirectory = $ProjectRoot
        PassThru = $true
    }
    $Process = Start-Process @StartProcessArgs
    $Process.Id | Out-File -FilePath $PidFile -Encoding utf8 -Force
    Write-Host "  Server process launched (PID: $($Process.Id))."
}

# Wait for server health
Write-Host "  Waiting for health check endpoint ($ServerUrl/health)..." -NoNewline
$MaxAttempts = 15
$Healthy = $false

for ($i = 1; $i -le $MaxAttempts; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $Resp = Invoke-RestMethod -Uri "$ServerUrl/health" -TimeoutSec 2 -ErrorAction Stop
        if ($Resp.status -eq "ok") {
            $Healthy = $true
            break
        }
    } catch {
        Write-Host "." -NoNewline
    }
}
Write-Host ""

if ($Healthy) {
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host " Server is READY at: $ServerUrl" -ForegroundColor Green
    Write-Host " Health Status: OK" -ForegroundColor Green
    Write-Host " User Data: $DataDir" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    if (-not $Headless) {
        Write-Host "Opening web browser..." -ForegroundColor Cyan
        Start-Process $ServerUrl
    }
} else {
    Write-Error "Server failed to respond to health check at $ServerUrl/health after $MaxAttempts attempts. Check logs at $ServerLog"
    exit 1
}
