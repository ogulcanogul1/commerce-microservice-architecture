# ==============================================================================
# Commerce Platform - Observability Stack Launcher (LGTM Stack)
# Starts Prometheus, Grafana Tempo (Tracing), Loki (Logging), Promtail, and Grafana UI
# Usage: .\scripts\monitoring-run.ps1 [-Down]
# ==============================================================================

param(
    [switch]$Down = $false
)

$ErrorActionPreference = "Stop"

$Cyan   = [System.ConsoleColor]::Cyan
$Green  = [System.ConsoleColor]::Green
$Yellow = [System.ConsoleColor]::Yellow
$White  = [System.ConsoleColor]::White
$Gray   = [System.ConsoleColor]::DarkGray

Write-Host "======================================================================" -ForegroundColor $Cyan
Write-Host "      COMMERCE PLATFORM - OBSERVABILITY STACK (LGTM STACK)            " -ForegroundColor $White
Write-Host "======================================================================" -ForegroundColor $Cyan

if ($Down) {
    Write-Host "Stopping monitoring containers..." -ForegroundColor $Yellow
    docker compose stop prometheus tempo loki promtail grafana
    Write-Host "[SUCCESS] Monitoring stack stopped." -ForegroundColor $Green
    exit 0
}

Write-Host "Starting Observability Containers (Prometheus, Tempo, Loki, Promtail, Grafana)..." -ForegroundColor $Yellow
docker compose up -d prometheus tempo loki promtail grafana

Write-Host "`nWaiting for observability containers to be ready..." -ForegroundColor $Gray
Start-Sleep -Seconds 3

Write-Host "`nObservability Access Endpoints:" -ForegroundColor $Cyan
Write-Host "  * Grafana Dashboard  : http://localhost:3000 (admin / admin)" -ForegroundColor $White
Write-Host "  * Prometheus Metrics : http://localhost:9090" -ForegroundColor $White
Write-Host "  * Tempo OTLP Traces  : http://localhost:4318 (HTTP) / :3200 (Query)" -ForegroundColor $White
Write-Host "  * Loki Log Engine    : http://localhost:3100" -ForegroundColor $White
Write-Host "======================================================================" -ForegroundColor $Cyan
