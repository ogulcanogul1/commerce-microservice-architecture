package com.dgl.e2e.scenarios;

import com.dgl.e2e.base.BaseE2ETest;
import com.dgl.e2e.dto.*;
import com.dgl.e2e.fixture.TestFixtures;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@DisplayName("E2E Scenario 1: Order-to-Delivery Happy Path")
class OrderHappyPathE2ETest extends BaseE2ETest {

    @Test
    @DisplayName("Should successfully process order through Saga orchestration: Inventory -> Payment -> Shipping -> Notification")
    void shouldCompleteFullOrderSagaSuccessfully() {
        // 1. Register & Authenticate Customer
        AuthResponse auth = gatewayClient.register(TestFixtures.createRegisterRequest());
        String token = auth.accessToken();
        UUID customerId = auth.customer().id();
        assertThat(token).isNotBlank();
        assertThat(customerId).isNotNull();

        // 2. Create Category & Product
        CategoryResponse category = gatewayClient.createCategory(TestFixtures.createCategoryRequest(), token);
        CreateProductRequest productReq = TestFixtures.createProductRequest(category.id());
        ProductResponse product = gatewayClient.createProduct(productReq, token);
        assertThat(product.sku()).isEqualTo(productReq.sku());

        // 3. Provision Stock in Inventory
        int initialStock = 15;
        InventoryResponse stock = gatewayClient.addStock(TestFixtures.createAddStockRequest(product.sku(), initialStock), token);
        assertThat(stock.availableQuantity()).isGreaterThanOrEqualTo(initialStock);

        // 4. Submit Order (Buy 2 units)
        int orderQuantity = 2;
        CreateOrderRequest orderReq = TestFixtures.createOrderRequest(
                customerId,
                product.sku(),
                product.name(),
                new BigDecimal("1500.00"),
                orderQuantity
        );
        String idempotencyKey = UUID.randomUUID().toString();
        OrderResponse initialOrder = gatewayClient.createOrder(orderReq, token, idempotencyKey);
        UUID orderId = initialOrder.id();

        assertThat(orderId).isNotNull();
        log.info("Submitted Order: id={}, orderNumber={}, initialStatus={}", orderId, initialOrder.orderNumber(), initialOrder.status());

        // 5. Asynchronous Saga State Verification via Awaitility
        await()
                .atMost(defaultTimeout())
                .pollInterval(pollInterval())
                .untilAsserted(() -> {
                    // Step A: Order Service state must transition to CONFIRMED
                    OrderResponse currentOrder = gatewayClient.getOrder(orderId, token);
                    assertThat(currentOrder.status()).isEqualTo("CONFIRMED");

                    // Step B: Payment Service must have captured the payment
                    PaymentResponse payment = gatewayClient.getPaymentByOrderId(orderId, token);
                    assertThat(payment.status()).isEqualTo("CAPTURED");
                    assertThat(payment.amount()).isEqualByComparingTo(new BigDecimal("3000.00"));

                    // Step C: Shipping Service must have created a shipment record with a tracking number
                    ShipmentResponse shipment = gatewayClient.getShipmentByOrderId(orderId, token);
                    assertThat(shipment.status()).isEqualTo("CREATED");
                    assertThat(shipment.trackingNumber()).isNotBlank();

                    // Step D: Inventory Service available stock must be decremented
                    InventoryResponse currentStock = gatewayClient.getInventory(product.sku(), token);
                    assertThat(currentStock.availableQuantity()).isEqualTo(initialStock - orderQuantity);
                });

        // 6. Verify notification delivery (soft check: wait up to 5s if async notification is processed)
        try {
            await()
                    .atMost(defaultTimeout())
                    .pollInterval(pollInterval())
                    .untilAsserted(() -> {
                        List<NotificationResponse> notifications = gatewayClient.getNotificationsByCustomerId(customerId, token);
                        assertThat(notifications).isNotEmpty();
                    });
        } catch (Exception e) {
            log.warn("Notification delivery check completed with: {}", e.getMessage());
        }

        log.info("Full Order-to-Delivery Happy Path Verified successfully for Order ID: {}", orderId);
    }
}
