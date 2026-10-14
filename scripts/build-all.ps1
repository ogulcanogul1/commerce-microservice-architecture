# ==============================================================================
# Commerce Platform - Maven Multi-Service Build Script
# Builds all 8 services with optional test skipping for fast packaging
# Usage: .\scripts\build-all.ps1 [-SkipTests]
# ==============================================================================

param(
    [switch]$SkipTests = $true
)

$ErrorActionPreference = "Stop"

$Services = @(
    "api-gateway",
    "product-service",
    "order-service",
    "payment-service",
    "inventory-service",
    "shipping-service",
    "customer-service",
    "notification-service"
)

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "       COMMERCE PLATFORM - MULTI-SERVICE BUILD PIPELINE               " -ForegroundColor White
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "Skip Tests : $SkipTests" -ForegroundColor Gray
Write-Host "Services   : $($Services.Count) microservices" -ForegroundColor Gray
Write-Host "----------------------------------------------------------------------" -ForegroundColor Gray

$StartTime = Get-Date

foreach ($service in $Services) {
    Write-Host "`n>>> Building $service..." -ForegroundColor Yellow
    Push-Location $service
    try {
        if ($SkipTests) {
            .\mvnw clean package -DskipTests
        } else {
            .\mvnw clean package
        }
        Write-Host "[SUCCESS] $service built successfully!" -ForegroundColor Green
    } catch {
        Write-Host "[ERROR] Failed building $service: $_" -ForegroundColor Red
        Pop-Location
        exit 1
    }
    Pop-Location
}

$Duration = [int]((Get-Date) - $StartTime).TotalSeconds
Write-Host "`n======================================================================" -ForegroundColor Cyan
Write-Host ">>> ALL $($Services.Count) SERVICES BUILT SUCCESSFULLY in ${Duration}s! <<<" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Cyan
