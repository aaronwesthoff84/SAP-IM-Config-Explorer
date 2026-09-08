<#
.SYNOPSIS
    Stops the running SAP IM Config Explorer server on Windows.

.DESCRIPTION
    Safely terminates the server process using the recorded PID file (.runtime\app.pid)
    or by locating any python/uvicorn process bound to the specified loopback port.
    Cleans up runtime files upon exit.

.PARAMETER Port
    TCP port used by the server (default: 8000).

.PARAMETER Force
    Force kill process immediately instead of graceful stop.
#>

[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$Force
)

$ErrorActionPreference = "Continue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Resolve-Path "$ScriptDir\..\.." -ErrorAction SilentlyContinue
if (-not $ProjectRoot -or -not (Test-Path "$ProjectRoot\sap_im_config_graph_explorer")) {
    $ProjectRoot = Resolve-Path "$ScriptDir\.." -ErrorAction SilentlyContinue
}
if (-not $ProjectRoot -or -not (Test-Path "$ProjectRoot\sap_im_config_graph_explorer")) {
    $ProjectRoot = Resolve-Path "$ScriptDir"
}
$ProjectRoot = $ProjectRoot.Path

$PidFile = Join-Path $ProjectRoot ".runtime\app.pid"
$Stopped = $false

Write-Host "Stopping SAP IM Config Explorer server..."

# 1. Check PID file
if (Test-Path $PidFile) {
    $TargetPid = (Get-Content $PidFile -ErrorAction SilentlyContinue).Trim()
    if ($TargetPid) {
        $Proc = Get-Process -Id $TargetPid -ErrorAction SilentlyContinue
        if ($Proc) {
            Write-Host "  Terminating process PID $TargetPid ($($Proc.ProcessName))..."
            if ($Force) {
                Stop-Process -Id $TargetPid -Force -ErrorAction SilentlyContinue
            } else {
                Stop-Process -Id $TargetPid -ErrorAction SilentlyContinue
            }
            $Stopped = $true
        }
    }
    Remove-Item -Path $PidFile -Force -ErrorAction SilentlyContinue
}

# 2. Check for any lingering process listening on the port
$PortConnections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($PortConnections) {
    foreach ($Conn in $PortConnections) {
        $ListeningPid = $Conn.OwningProcess
        if ($ListeningPid -and $ListeningPid -ne 0 -and $ListeningPid -ne 4) {
            $Proc = Get-Process -Id $ListeningPid -ErrorAction SilentlyContinue
            if ($Proc -and ($Proc.ProcessName -match "python" -or $Proc.ProcessName -match "uvicorn")) {
                Write-Host "  Stopping lingering process on port ${Port} (PID: $ListeningPid, $($Proc.ProcessName))..."
                Stop-Process -Id $ListeningPid -Force -ErrorAction SilentlyContinue
                $Stopped = $true
            }
        }
    }
}

if ($Stopped) {
    Write-Host "Server successfully stopped." -ForegroundColor Green
    exit 0
} else {
    Write-Host "No active SAP IM Config Explorer server was found running on port $Port." -ForegroundColor Yellow
    exit 0
}
