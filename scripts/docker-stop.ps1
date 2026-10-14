# ==============================================================================
# Commerce Platform - Docker Compose Teardown Script
# Stops all platform containers and networks gracefully
# Usage: .\scripts\docker-stop.ps1 [-Volumes]
# ==============================================================================

param(
    [switch]$Volumes = $false
)

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "          COMMERCE PLATFORM - STOPPING ALL CONTAINERS                 " -ForegroundColor White
Write-Host "======================================================================" -ForegroundColor Cyan

if ($Volumes) {
    Write-Host "Stopping containers and REMOVING all persistent volumes (Fresh Start)..." -ForegroundColor Yellow
    docker compose -f docker-compose.yml -f docker-compose.apps.yml down -v
} else {
    Write-Host "Stopping containers (preserving database volumes)..." -ForegroundColor Yellow
    docker compose -f docker-compose.yml -f docker-compose.apps.yml down
}

Write-Host "`nAll platform containers stopped successfully." -ForegroundColor Green
