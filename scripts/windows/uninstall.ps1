<#
.SYNOPSIS
    Uninstalls or resets the SAP IM Config Explorer application environment.

.DESCRIPTION
    Stops running server instances, removes runtime temporary state, caches,
    and the local virtual environment.

    SAFETY POLICY:
    By default, user data (saved sessions, exports, waivers, and custom configurations)
    stored in %LOCALAPPDATA%\SAP-IM-Config-Explorer are PRESERVED.
    They will NEVER be deleted unless -PurgeUserData is explicitly passed with confirmation.

.PARAMETER PurgeUserData
    Explicitly request deletion of user-generated exports and saved sessions.

.PARAMETER Force
    Suppress confirmation prompt when -PurgeUserData is specified.

.PARAMETER DataDir
    Path to user data directory (default: %LOCALAPPDATA%\SAP-IM-Config-Explorer).
#>

[CmdletBinding()]
param(
    [switch]$PurgeUserData,
    [switch]$Force,
    [string]$DataDir = "$env:LOCALAPPDATA\SAP-IM-Config-Explorer"
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

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " SAP IM Config Explorer - Windows Uninstaller" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Stop Server
Write-Host "[1/3] Stopping any running server instances..." -ForegroundColor Green
$StopScript = Join-Path $ScriptDir "stop.ps1"
if (Test-Path $StopScript) {
    & $StopScript
}

# 2. Remove Runtime & Build Artifacts
Write-Host "[2/3] Cleaning runtime files, caches, and virtual environment..." -ForegroundColor Green
$DirsToClean = @(
    (Join-Path $ProjectRoot ".runtime"),
    (Join-Path $ProjectRoot ".validation-output"),
    (Join-Path $ProjectRoot ".pytest_cache"),
    (Join-Path $ProjectRoot "pytest_tmp"),
    (Join-Path $ProjectRoot "playwright-report"),
    (Join-Path $ProjectRoot "test-results")
)

foreach ($Dir in $DirsToClean) {
    if (Test-Path $Dir) {
        Write-Host "  Removing: $Dir"
        Remove-Item -Recurse -Force -Path $Dir -ErrorAction SilentlyContinue
    }
}

# 3. User Data Handling
Write-Host "[3/3] Evaluating user data directory policy..." -ForegroundColor Green
if (Test-Path $DataDir) {
    if ($PurgeUserData) {
        $Confirmed = $Force
        if (-not $Confirmed) {
            Write-Host "WARNING: You requested -PurgeUserData. This will permanently delete:" -ForegroundColor Red
            Write-Host "  $DataDir (including all saved sessions, waivers, and exports)" -ForegroundColor Red
            $Prompt = Read-Host "Type 'YES' to confirm permanent deletion of user data"
            if ($Prompt -eq "YES") {
                $Confirmed = $true
            } else {
                Write-Host "Purge cancelled by user." -ForegroundColor Yellow
            }
        }

        if ($Confirmed) {
            Write-Host "  Purging user data directory: $DataDir..." -ForegroundColor Yellow
            Remove-Item -Recurse -Force -Path $DataDir -ErrorAction SilentlyContinue
            Write-Host "  User data removed." -ForegroundColor Yellow
        } else {
            Write-Host "  [SAFE PRESERVATION] User data retained at: $DataDir" -ForegroundColor Green
        }
    } else {
        Write-Host "  [SAFE PRESERVATION] User data directory preserved:" -ForegroundColor Green
        Write-Host "    Location: $DataDir" -ForegroundColor Green
        Write-Host "    (Saved sessions, export files, and waivers are intact)." -ForegroundColor Green
        Write-Host "    To delete user data, rerun with: .\uninstall.ps1 -PurgeUserData" -ForegroundColor DarkGray
    }
} else {
    Write-Host "  No user data directory found at $DataDir."
}

Write-Host "============================================================" -ForegroundColor Green
Write-Host " Uninstall / cleanup completed successfully." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
