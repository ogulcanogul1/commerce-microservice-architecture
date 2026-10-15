# ==============================================================================
# Commerce Platform - Debezium CDC Connectors Registration Script
# Registers and verifies PostgreSQL CDC Outbox Event Connectors via Kafka Connect REST API
# Usage: .\scripts\debezium-register.ps1 [-ConnectUrl "http://localhost:8088"] [-StatusOnly]
# ==============================================================================

param(
    [string]$ConnectUrl = "http://localhost:8088",
    [switch]$StatusOnly = $false
)

$ErrorActionPreference = "Continue"

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "        COMMERCE PLATFORM - DEBEZIUM OUTBOX CONNECTOR REGISTRATION    " -ForegroundColor White
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "Kafka Connect URL: $ConnectUrl`n" -ForegroundColor Gray

# Wait for Kafka Connect REST API to become ready
Write-Host "Checking Kafka Connect availability at $ConnectUrl..." -ForegroundColor Yellow
$maxRetries = 20
$attempt = 0
$ready = $false

while ($attempt -lt $maxRetries) {
    $attempt++
    try {
        $response = Invoke-RestMethod -Uri "$ConnectUrl/connectors" -Method Get -TimeoutSec 3 -ErrorAction Stop
        $ready = $true
        break
    } catch {
        Write-Host "Kafka Connect not ready yet (attempt $attempt/$maxRetries)... waiting 3s" -ForegroundColor DarkGray
        Start-Sleep -Seconds 3
    }
}

if (-not $ready) {
    Write-Host "Error: Unable to reach Kafka Connect at $ConnectUrl after $maxRetries attempts." -ForegroundColor Red
    Write-Host "Please ensure Kafka Connect container is running: docker compose ps kafka-connect" -ForegroundColor Yellow
    exit 1
}

Write-Host "Kafka Connect is ready and responsive!`n" -ForegroundColor Green

$connectorsDir = Join-Path $PSScriptRoot "..\docker\debezium\connectors"

if (-not $StatusOnly) {
    Write-Host "Registering Debezium Outbox Connectors from $connectorsDir..." -ForegroundColor Cyan

    $connectorFiles = Get-ChildItem -Path $connectorsDir -Filter "*.json"
    foreach ($file in $connectorFiles) {
        $content = Get-Content -Raw -Path $file.FullName | ConvertFrom-Json
        $connectorName = $content.name
        $connectorConfig = $content.config

        Write-Host "Configuring connector: [$connectorName]..." -NoNewline -ForegroundColor White

        try {
            $jsonBody = $connectorConfig | ConvertTo-Json -Depth 5
            # Use PUT /connectors/{name}/config for idempotent register/update
            $res = Invoke-RestMethod -Uri "$ConnectUrl/connectors/$connectorName/config" `
                                     -Method Put `
                                     -ContentType "application/json" `
                                     -Body $jsonBody `
                                     -ErrorAction Stop

            Write-Host " [OK - REGISTERED]" -ForegroundColor Green
        } catch {
            Write-Host " [FAILED]" -ForegroundColor Red
            Write-Host "  Error: $_" -ForegroundColor DarkRed
        }
    }
    Write-Host ""
}

# Display Connector Statuses
Write-Host "Active Connectors & Health Status:" -ForegroundColor Cyan
try {
    $connectors = Invoke-RestMethod -Uri "$ConnectUrl/connectors" -Method Get
    if ($connectors.Count -eq 0) {
        Write-Host "  No connectors currently registered." -ForegroundColor Yellow
    } else {
        foreach ($name in $connectors) {
            try {
                $status = Invoke-RestMethod -Uri "$ConnectUrl/connectors/$name/status" -Method Get
                $state = $status.connector.state
                $tasksCount = $status.tasks.Count
                $taskState = if ($tasksCount -gt 0) { $status.tasks[0].state } else { "NO_TASKS" }

                $color = if ($state -eq "RUNNING" -and $taskState -eq "RUNNING") { "Green" } else { "Yellow" }
                Write-Host "  * $name: Connector=[$state], Tasks=[$taskState ($tasksCount)]" -ForegroundColor $color
            } catch {
                Write-Host "  * $name: [Status query failed]" -ForegroundColor Red
            }
        }
    }
} catch {
    Write-Host "Failed to list connectors: $_" -ForegroundColor Red
}

Write-Host "`n======================================================================" -ForegroundColor Cyan
Write-Host "Debezium Outbox CDC Setup is active." -ForegroundColor Green
Write-Host "Kafka Connect REST API: $ConnectUrl/connectors" -ForegroundColor White
Write-Host "======================================================================" -ForegroundColor Cyan
