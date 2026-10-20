package com.dgl.e2e.scenarios;

import com.dgl.e2e.base.BaseE2ETest;
import com.dgl.e2e.dto.*;
import com.dgl.e2e.fixture.TestFixtures;
import io.restassured.response.Response;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@DisplayName("E2E Scenario 3: Payment Failure & Inventory Rollback Compensation")
class PaymentFailureRollbackE2ETest extends BaseE2ETest {

    @Test
    @DisplayName("Should release reserved inventory back to available stock when downstream payment fails")
    void shouldRollbackInventoryWhenPaymentFails() {
        // 1. Register & Authenticate Customer
        AuthResponse auth = gatewayClient.register(TestFixtures.createRegisterRequest());
        String token = auth.accessToken();
        UUID customerId = auth.customer().id();

        // 2. Create Category & Product
        CategoryResponse category = gatewayClient.createCategory(TestFixtures.createCategoryRequest(), token);
        CreateProductRequest productReq = TestFixtures.createProductRequest(category.id());
        ProductResponse product = gatewayClient.createProduct(productReq, token);

        // 3. Provision 5 units of stock
        int initialStock = 5;
        gatewayClient.addStock(TestFixtures.createAddStockRequest(product.sku(), initialStock), token);
        InventoryResponse stockBefore = gatewayClient.getInventory(product.sku(), token);
        assertThat(stockBefore.availableQuantity()).isEqualTo(initialStock);

        // 4. Submit Order with amount exceeding credit limit (e.g. 60,000.00 TL)
        // This triggers downstream PaymentFailedException in payment-service
        int orderQuantity = 1;
        BigDecimal highAmountPrice = new BigDecimal("60000.00");
        CreateOrderRequest orderReq = TestFixtures.createOrderRequest(
                customerId,
                product.sku(),
                product.name(),
                highAmountPrice,
                orderQuantity
        );
        OrderResponse initialOrder = gatewayClient.createOrder(orderReq, token, UUID.randomUUID().toString());
        UUID orderId = initialOrder.id();

        log.info("Submitted High-Value Order that triggers payment decline: id={}, amount={}",
                orderId, highAmountPrice);

        // 5. Asynchronous Saga Compensation Verification via Awaitility
        await()
                .atMost(defaultTimeout())
                .pollInterval(pollInterval())
                .untilAsserted(() -> {
                    // A: Order Service must transition to CANCELLED
                    OrderResponse currentOrder = gatewayClient.getOrder(orderId, token);
                    assertThat(currentOrder.status()).isEqualTo("CANCELLED");
                    assertThat(currentOrder.failureReason())
                            .isNotNull()
                            .containsIgnoringCase("payment");

                    // B: Inventory Service must have released reserved stock back to 5 units!
                    InventoryResponse restoredStock = gatewayClient.getInventory(product.sku(), token);
                    assertThat(restoredStock.availableQuantity()).isEqualTo(initialStock);

                    // C: Shipping Service must never have created a shipment record
                    Response shipmentResp = gatewayClient.getShipmentByOrderIdRaw(orderId, token);
                    assertThat(shipmentResp.statusCode()).isEqualTo(404);
                });

        log.info("Saga Compensation correctly rolled back stock to {} units after payment failure for Order ID: {}",
                initialStock, orderId);
    }
}
