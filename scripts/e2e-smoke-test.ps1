# ==============================================================================
# Commerce Platform - Automated End-to-End (E2E) Smoke Test Suite
# Tests: Gateway Routing, Auth, Redis Caching, Saga Orchestration, Compensation, Edge Security
# Usage: .\scripts\e2e-smoke-test.ps1 [-GatewayUrl "http://localhost:8080"]
# ==============================================================================

param(
    [string]$GatewayUrl = "http://localhost:8080",
    [int]$PollTimeoutSeconds = 20
)

$ErrorActionPreference = "Continue"

# ANSI Colors
$Green  = [System.ConsoleColor]::Green
$Red    = [System.ConsoleColor]::Red
$Cyan   = [System.ConsoleColor]::Cyan
$Yellow = [System.ConsoleColor]::Yellow
$White  = [System.ConsoleColor]::White
$Gray   = [System.ConsoleColor]::DarkGray

Write-Host ""
Write-Host "======================================================================" -ForegroundColor $Cyan
Write-Host "      COMMERCE PLATFORM - E2E AUTOMATED SMOKE TEST SUITE              " -ForegroundColor $White
Write-Host "======================================================================" -ForegroundColor $Cyan
Write-Host "Target Gateway URL: $GatewayUrl" -ForegroundColor $Gray
Write-Host "Timestamp         : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor $Gray
Write-Host "----------------------------------------------------------------------" -ForegroundColor $Gray

$TestResults = @()
$PassedCount = 0
$FailedCount = 0

function Report-Step {
    param(
        [string]$Name,
        [bool]$Success,
        [string]$Details = ""
    )
    if ($Success) {
        $script:PassedCount++
        Write-Host " [PASS] " -ForegroundColor $Green -NoNewline
        Write-Host "$Name" -ForegroundColor $White
        if ($Details) {
            Write-Host "        -> $Details" -ForegroundColor $Gray
        }
        $script:TestResults += [PSCustomObject]@{ Step = $Name; Status = "PASS"; Details = $Details }
    } else {
        $script:FailedCount++
        Write-Host " [FAIL] " -ForegroundColor $Red -NoNewline
        Write-Host "$Name" -ForegroundColor $White
        if ($Details) {
            Write-Host "        -> $Details" -ForegroundColor $Red
        }
        $script:TestResults += [PSCustomObject]@{ Step = $Name; Status = "FAIL"; Details = $Details }
    }
}

# -----------------------------------------------------------------------------
# STEP 1: Gateway Health Check
# -----------------------------------------------------------------------------
Write-Host "`n1. Checking API Gateway Health..." -ForegroundColor $Yellow
try {
    $healthResp = Invoke-RestMethod -Uri "$GatewayUrl/actuator/health" -Method Get -TimeoutSec 5
    $isUp = ($healthResp.status -eq "UP")
    Report-Step -Name "Gateway Health Check" -Success $isUp -Details "Status: $($healthResp.status)"
} catch {
    Report-Step -Name "Gateway Health Check" -Success $false -Details "Could not reach Gateway at $GatewayUrl. Ensure services or Docker containers are running!"
    Write-Host "`n[FATAL] Gateway unreachable. Terminating test suite." -ForegroundColor $Red
    exit 1
}

# -----------------------------------------------------------------------------
# STEP 2: Customer Registration & JWT Issuance
# -----------------------------------------------------------------------------
Write-Host "`n2. Registering Customer & Authenticating..." -ForegroundColor $Yellow
$UniqueId = [System.Guid]::NewGuid().ToString().Substring(0, 8)
$TestEmail = "tester_$UniqueId@example.com"
$AuthToken = ""
$CustomerId = ""

try {
    $regBody = @{
        email = $TestEmail
        password = "Password123!"
        firstName = "Smoke"
        lastName = "Tester"
        phoneNumber = "+905550000000"
    } | ConvertTo-Json

    $regResp = Invoke-RestMethod -Uri "$GatewayUrl/api/v1/auth/register" -Method Post -Body $regBody -ContentType "application/json"
    $AuthToken = $regResp.accessToken
    $CustomerId = $regResp.customer.id
    $hasToken = ($AuthToken -and $CustomerId)
    Report-Step -Name "Customer Registration & Token Generation" -Success $hasToken -Details "User: $TestEmail | CustomerId: $CustomerId"
} catch {
    Report-Step -Name "Customer Registration & Token Generation" -Success $false -Details $_.Exception.Message
}

$AuthHeaders = @{
    "Authorization" = "Bearer $AuthToken"
    "Content-Type" = "application/json"
}

# -----------------------------------------------------------------------------
# STEP 3: Product Category & Product Catalog Creation
# -----------------------------------------------------------------------------
Write-Host "`n3. Provisioning Catalog (Product Service & Redis Cache)..." -ForegroundColor $Yellow
$CategoryId = ""
$ProductSku = "SKU-AUTO-$UniqueId"

try {
    $catBody = @{
        name = "Smoke Electronics $UniqueId"
        description = "Automated test category"
    } | ConvertTo-Json

    $catResp = Invoke-RestMethod -Uri "$GatewayUrl/api/v1/categories" -Method Post -Headers $AuthHeaders -Body $catBody
    $CategoryId = $catResp.id
    Report-Step -Name "Category Creation" -Success ([bool]$CategoryId) -Details "CategoryId: $CategoryId"

    $prodBody = @{
        sku = $ProductSku
        name = "High-End Laptop $UniqueId"
        description = "M3 Max 32GB RAM"
        categoryId = $CategoryId
        basePrice = 54999.00
        currency = "TRY"
    } | ConvertTo-Json

    $prodResp = Invoke-RestMethod -Uri "$GatewayUrl/api/v1/products" -Method Post -Headers $AuthHeaders -Body $prodBody
    $prodCreated = ($prodResp.sku -eq $ProductSku)
    Report-Step -Name "Product Catalog Entry Creation" -Success $prodCreated -Details "SKU: $ProductSku | Price: 54999.00 TRY"
} catch {
    Report-Step -Name "Product & Category Provisioning" -Success $false -Details $_.Exception.Message
}

# -----------------------------------------------------------------------------
# STEP 4: Inventory Stock Management
# -----------------------------------------------------------------------------
Write-Host "`n4. Adding Inventory Stock..." -ForegroundColor $Yellow
try {
    $stockBody = @{
        sku = $ProductSku
        quantity = 25
    } | ConvertTo-Json

    $stockResp = Invoke-RestMethod -Uri "$GatewayUrl/api/v1/inventory/add" -Method Post -Headers $AuthHeaders -Body $stockBody
    $stockAdded = ($stockResp.quantity -ge 25)
    Report-Step -Name "Inventory Stock Provisioning" -Success $stockAdded -Details "Available Stock: $($stockResp.quantity)"
} catch {
    Report-Step -Name "Inventory Stock Provisioning" -Success $false -Details $_.Exception.Message
}

# -----------------------------------------------------------------------------
# STEP 5 & 6: Order Placement & Saga Orchestration (Happy Path)
# -----------------------------------------------------------------------------
Write-Host "`n5. Submitting Order & Triggering Distributed Saga Orchestration..." -ForegroundColor $Yellow
$OrderId = ""
$OrderNumber = ""

try {
    $orderBody = @{
        customerId = $CustomerId
        shippingAddress = "Atatürk Bulvarı No:100 Çankaya / Ankara"
        currency = "TRY"
        items = @(
            @{
                sku = $ProductSku
                productName = "High-End Laptop $UniqueId"
                unitPrice = 54999.00
                quantity = 1
            }
        )
    } | ConvertTo-Json

    $orderResp = Invoke-RestMethod -Uri "$GatewayUrl/api/v1/orders" -Method Post -Headers $AuthHeaders -Body $orderBody
    $OrderId = $orderResp.id
    $OrderNumber = $orderResp.orderNumber
    Report-Step -Name "Order Placement & Saga Trigger" -Success ([bool]$OrderId) -Details "OrderId: $OrderId | OrderNo: $OrderNumber | Initial Status: $($orderResp.status)"
} catch {
    Report-Step -Name "Order Placement & Saga Trigger" -Success $false -Details $_.Exception.Message
}

Write-Host "   Polling order state machine for CONFIRMED status..." -ForegroundColor $Gray
$SagaConfirmed = $false
$FinalStatus = ""
$PollStart = Get-Date

if ($OrderId) {
    while (((Get-Date) - $PollStart).TotalSeconds -lt $PollTimeoutSeconds) {
        Start-Sleep -Seconds 1
        try {
            $checkResp = Invoke-RestMethod -Uri "$GatewayUrl/api/v1/orders/$OrderId" -Method Get -Headers $AuthHeaders
            $FinalStatus = $checkResp.status
            if ($FinalStatus -eq "CONFIRMED") {
                $SagaConfirmed = $true
                break
            } elseif ($FinalStatus -in @("CANCELLED", "INVENTORY_FAILED", "PAYMENT_FAILED", "SHIPPING_FAILED")) {
                break
            }
        } catch {}
    }
}

Report-Step -Name "Saga Orchestration Workflow" -Success $SagaConfirmed -Details "Final Status: $FinalStatus (Elapsed: $([int]((Get-Date) - $PollStart).TotalSeconds)s)"

# -----------------------------------------------------------------------------
# STEP 7: Downstream Verifications (Payment, Shipping, Notification)
# -----------------------------------------------------------------------------
Write-Host "`n6. Verifying Downstream Saga State..." -ForegroundColor $Yellow
if ($OrderId) {
    try {
        $payResp = Invoke-RestMethod -Uri "$GatewayUrl/api/v1/payments/order/$OrderId" -Method Get -Headers $AuthHeaders
        $isCaptured = ($payResp.status -eq "CAPTURED")
        Report-Step -Name "Payment Verification" -Success $isCaptured -Details "Payment Status: $($payResp.status) | Amount: $($payResp.amount)"
    } catch {
        Report-Step -Name "Payment Verification" -Success $false -Details $_.Exception.Message
    }

    try {
        $shipResp = Invoke-RestMethod -Uri "$GatewayUrl/api/v1/shipments/order/$OrderId" -Method Get -Headers $AuthHeaders
        $hasTracking = ($shipResp.trackingNumber -and $shipResp.status -eq "CREATED")
        Report-Step -Name "Shipment Verification" -Success $hasTracking -Details "Shipment: $($shipResp.status) | Tracking: $($shipResp.trackingNumber)"
    } catch {
        Report-Step -Name "Shipment Verification" -Success $false -Details $_.Exception.Message
    }

    try {
        $notifResp = Invoke-RestMethod -Uri "$GatewayUrl/api/v1/notifications/customer/$CustomerId" -Method Get -Headers $AuthHeaders
        $hasNotif = ($notifResp.Count -gt 0)
        Report-Step -Name "Notification Delivery Verification" -Success $hasNotif -Details "Total Notifications Delivered: $($notifResp.Count)"
    } catch {
        Report-Step -Name "Notification Delivery Verification" -Success $false -Details $_.Exception.Message
    }
}

# -----------------------------------------------------------------------------
# STEP 8: Compensation Path (Insufficient Stock)
# -----------------------------------------------------------------------------
Write-Host "`n7. Testing Saga Compensation Path (Insufficient Stock)..." -ForegroundColor $Yellow
try {
    $failOrderBody = @{
        customerId = $CustomerId
        shippingAddress = "Compensation Test Address"
        currency = "TRY"
        items = @(
            @{
                sku = $ProductSku
                productName = "High-End Laptop $UniqueId"
                unitPrice = 54999.00
                quantity = 99999
            }
        )
    } | ConvertTo-Json

    $failResp = Invoke-RestMethod -Uri "$GatewayUrl/api/v1/orders" -Method Post -Headers $AuthHeaders -Body $failOrderBody
    $FailOrderId = $failResp.id

    # Wait for compensation to transition order to CANCELLED
    $Compensated = $false
    $FailPollStart = Get-Date
    while (((Get-Date) - $FailPollStart).TotalSeconds -lt 10) {
        Start-Sleep -Seconds 1
        try {
            $checkFail = Invoke-RestMethod -Uri "$GatewayUrl/api/v1/orders/$FailOrderId" -Method Get -Headers $AuthHeaders
            if ($checkFail.status -eq "CANCELLED") {
                $Compensated = $true
                break
            }
        } catch {}
    }
    Report-Step -Name "Saga Compensation Path" -Success $Compensated -Details "Stock-exceeding order cancelled automatically by Saga Orchestrator"
} catch {
    Report-Step -Name "Saga Compensation Path" -Success $false -Details $_.Exception.Message
}

# -----------------------------------------------------------------------------
# STEP 9: Edge Security (Missing Token)
# -----------------------------------------------------------------------------
Write-Host "`n8. Testing Edge Security & Authorization Filter..." -ForegroundColor $Yellow
try {
    $unauthBody = @{ customerId = "00000000-0000-0000-0000-000000000000"; items = @() } | ConvertTo-Json
    $null = Invoke-RestMethod -Uri "$GatewayUrl/api/v1/orders" -Method Post -Body $unauthBody -ContentType "application/json"
    Report-Step -Name "Edge Security (401 on Missing Token)" -Success $false -Details "Expected HTTP 401 but request succeeded"
} catch {
    $statusCode = $_.Exception.Response.StatusCode.value__
    $is401 = ($statusCode -eq 401)
    Report-Step -Name "Edge Security (401 on Missing Token)" -Success $is401 -Details "HTTP Status: $statusCode (Correctly rejected unauthorized request)"
}

# -----------------------------------------------------------------------------
# STEP 10: Circuit Breaker Fallback
# -----------------------------------------------------------------------------
Write-Host "`n9. Testing Circuit Breaker Fallback Endpoint..." -ForegroundColor $Yellow
try {
    $fallbackResp = Invoke-RestMethod -Uri "$GatewayUrl/fallback/product" -Method Get
    $hasFallbackMessage = ($fallbackResp.message -or $fallbackResp.detail)
    Report-Step -Name "Circuit Breaker Fallback Endpoint" -Success ([bool]$hasFallbackMessage) -Details "Fallback response received gracefully"
} catch {
    Report-Step -Name "Circuit Breaker Fallback Endpoint" -Success $false -Details $_.Exception.Message
}

# -----------------------------------------------------------------------------
# FINAL REPORT SUMMARY
# -----------------------------------------------------------------------------
Write-Host ""
Write-Host "======================================================================" -ForegroundColor $Cyan
Write-Host "                      E2E TEST SUMMARY REPORT                         " -ForegroundColor $White
Write-Host "======================================================================" -ForegroundColor $Cyan
Write-Host "Total Tests : $($PassedCount + $FailedCount)" -ForegroundColor $White
Write-Host "Passed      : $PassedCount" -ForegroundColor $Green
Write-Host "Failed      : $FailedCount" -ForegroundColor $(if ($FailedCount -gt 0) { $Red } else { $Green })
Write-Host "----------------------------------------------------------------------" -ForegroundColor $Gray

if ($FailedCount -eq 0) {
    Write-Host ">>> ALL END-TO-END TESTS PASSED SUCCESSFULLY! <<<" -ForegroundColor $Green
    Write-Host ""
    exit 0
} else {
    Write-Host ">>> SOME TESTS FAILED. PLEASE CHECK DETAILED LOGS ABOVE. <<<" -ForegroundColor $Red
    Write-Host ""
    exit 1
}
