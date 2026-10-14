# ==============================================================================
# Commerce Platform - Docker Compose Launch Script
# Launches full platform: Infrastructure + 8 Application Microservices
# Usage: .\scripts\docker-run.ps1 [-Build] [-InfraOnly]
# ==============================================================================

param(
    [switch]$Build = $false,
    [switch]$InfraOnly = $false
)

$ErrorActionPreference = "Stop"

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "          COMMERCE PLATFORM - DOCKER COMPOSE ORCHESTRATOR             " -ForegroundColor White
Write-Host "======================================================================" -ForegroundColor Cyan

if ($InfraOnly) {
    Write-Host "Starting INFRASTRUCTURE only (PostgreSQL, Kafka, Redis, LGTM Stack)..." -ForegroundColor Yellow
    docker compose -f docker-compose.yml up -d
} else {
    Write-Host "Starting FULL PLATFORM (Infra + 8 Application Microservices)..." -ForegroundColor Yellow
    if ($Build) {
        docker compose -f docker-compose.yml -f docker-compose.apps.yml up -d --build
    } else {
        docker compose -f docker-compose.yml -f docker-compose.apps.yml up -d
    }
}

Write-Host "`nWaiting for containers to initialize..." -ForegroundColor Gray
Start-Sleep -Seconds 5
docker compose -f docker-compose.yml -f docker-compose.apps.yml ps

Write-Host "`nPlatform Access URLs:" -ForegroundColor Cyan
Write-Host "  Eureka Server Dashboard  : http://localhost:8761" -ForegroundColor White
Write-Host "  API Gateway & Swagger UI : http://localhost:8080/swagger-ui.html" -ForegroundColor White
Write-Host "  Kafka UI Web Console     : http://localhost:8090" -ForegroundColor White
Write-Host "  Grafana Observability    : http://localhost:3000 (admin / admin)" -ForegroundColor White
Write-Host "  Prometheus Metrics       : http://localhost:9090" -ForegroundColor White
Write-Host "======================================================================" -ForegroundColor Cyan
