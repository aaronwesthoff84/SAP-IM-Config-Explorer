<#
.SYNOPSIS
    Builds the reproducible offline Windows distribution ZIP for SAP IM Config Explorer.

.DESCRIPTION
    Runs scripts/package_offline.py using the active Python environment, packages all
    vendored assets, manifests, licenses, and launchers, optionally downloads wheels
    for offline execution, and writes the output archive to dist/.

.PARAMETER DownloadWheels
    If specified, downloads pip wheels for all requirements into wheels/ before packaging.

.PARAMETER OutputDir
    Custom destination directory for the generated ZIP (default: dist/).
#>

[CmdletBinding()]
param(
    [switch]$DownloadWheels,
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Resolve-Path "$ScriptDir\..\.." -ErrorAction SilentlyContinue
if (-not $ProjectRoot -or -not (Test-Path "$ProjectRoot\sap_im_config_graph_explorer")) {
    $ProjectRoot = Resolve-Path "$ScriptDir\.." -ErrorAction SilentlyContinue
}
$ProjectRoot = $ProjectRoot.Path

# Locate Python
$PythonExe = "$ProjectRoot\.venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
}

if (-not $PythonExe) {
    Write-Error "Python runtime not found. Please activate .venv or install Python 3.10+."
    exit 1
}

$WheelsDir = Join-Path $ProjectRoot "wheels"

if ($DownloadWheels) {
    Write-Host "Downloading offline runtime wheels for requirements.txt..." -ForegroundColor Green
    New-Item -ItemType Directory -Force -Path $WheelsDir | Out-Null
    & $PythonExe -m pip download -r "$ProjectRoot\requirements.txt" -d "$WheelsDir"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to download offline wheels."
        exit 1
    }
}

$PackageScript = Join-Path $ProjectRoot "scripts\package_offline.py"
$BuildArgs = @($PackageScript)

if ($OutputDir) {
    $BuildArgs += @("--output-dir", $OutputDir)
}
if (Test-Path $WheelsDir) {
    $BuildArgs += @("--wheels-dir", $WheelsDir)
}

Write-Host "Executing package builder..." -ForegroundColor Green
& $PythonExe @BuildArgs

if ($LASTEXITCODE -eq 0) {
    Write-Host "Packaging completed successfully." -ForegroundColor Green
} else {
    Write-Error "Packaging encountered an error (exit code $LASTEXITCODE)."
    exit $LASTEXITCODE
}
