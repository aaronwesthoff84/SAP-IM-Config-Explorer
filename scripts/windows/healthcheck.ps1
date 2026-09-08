<#
.SYNOPSIS
    Runs a health check against the local SAP IM Config Explorer instance.

.DESCRIPTION
    Sends an HTTP GET request to the loopback health endpoint (http://127.0.0.1:<port>/health)
    and verifies that the service is running, responsive, and returning {"status": "ok"}.
    Returns exit code 0 on success, or 1 on failure.

.PARAMETER Port
    TCP port to query (default: 8000).

.PARAMETER HostAddress
    Host address to query (default: "127.0.0.1").

.PARAMETER TimeoutSec
    Timeout in seconds (default: 5).

.PARAMETER Quiet
    If specified, suppresses informational console output.
#>

[CmdletBinding()]
param(
    [int]$Port = 8000,
    [string]$HostAddress = "127.0.0.1",
    [int]$TimeoutSec = 5,
    [switch]$Quiet
)

$HealthUrl = "http://${HostAddress}:${Port}/health"

if (-not $Quiet) {
    Write-Host "Querying health endpoint: $HealthUrl (Timeout: ${TimeoutSec}s)..."
}

$Stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

try {
    $Response = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec $TimeoutSec -ErrorAction Stop
    $Stopwatch.Stop()

    if ($Response.status -eq "ok") {
        if (-not $Quiet) {
            Write-Host "HEALTH CHECK: PASS" -ForegroundColor Green
            Write-Host "  Endpoint: $HealthUrl"
            Write-Host "  Status: $($Response.status)"
            Write-Host "  Latency: $($Stopwatch.ElapsedMilliseconds) ms"
        }
        exit 0
    } else {
        if (-not $Quiet) {
            Write-Host "HEALTH CHECK: UNEXPECTED RESPONSE" -ForegroundColor Yellow
            Write-Host "  Endpoint: $HealthUrl"
            Write-Host "  Payload: $($Response | ConvertTo-Json -Compress)"
        }
        exit 1
    }
} catch {
    $Stopwatch.Stop()
    if (-not $Quiet) {
        Write-Host "HEALTH CHECK: FAIL" -ForegroundColor Red
        Write-Host "  Endpoint: $HealthUrl"
        Write-Host "  Error: $($_.Exception.Message)"
        Write-Host "  Latency: $($Stopwatch.ElapsedMilliseconds) ms"
    }
    exit 1
}
