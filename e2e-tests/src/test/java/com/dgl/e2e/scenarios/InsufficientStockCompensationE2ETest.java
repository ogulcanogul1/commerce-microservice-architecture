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

@DisplayName("E2E Scenario 2: Insufficient Stock Saga Compensation")
class InsufficientStockCompensationE2ETest extends BaseE2ETest {

    @Test
    @DisplayName("Should abort order and trigger Saga compensation when requested quantity exceeds available stock")
    void shouldCancelOrderWhenStockIsInsufficient() {
        // 1. Register & Authenticate Customer
        AuthResponse auth = gatewayClient.register(TestFixtures.createRegisterRequest());
        String token = auth.accessToken();
        UUID customerId = auth.customer().id();

        // 2. Create Category & Product
        CategoryResponse category = gatewayClient.createCategory(TestFixtures.createCategoryRequest(), token);
        CreateProductRequest productReq = TestFixtures.createProductRequest(category.id());
        ProductResponse product = gatewayClient.createProduct(productReq, token);

        // 3. Add only 2 units of stock
        int availableStock = 2;
        gatewayClient.addStock(TestFixtures.createAddStockRequest(product.sku(), availableStock), token);

        // 4. Request 100 units (insufficient inventory)
        int excessiveQuantity = 100;
        CreateOrderRequest orderReq = TestFixtures.createOrderRequest(
                customerId,
                product.sku(),
                product.name(),
                new BigDecimal("1500.00"),
                excessiveQuantity
        );
        OrderResponse initialOrder = gatewayClient.createOrder(orderReq, token, UUID.randomUUID().toString());
        UUID orderId = initialOrder.id();

        log.info("Submitted Excessive Order: id={}, quantityRequested={}", orderId, excessiveQuantity);

        // 5. Asynchronous Saga Compensation Verification
        await()
                .atMost(defaultTimeout())
                .pollInterval(pollInterval())
                .untilAsserted(() -> {
                    // Order must transition to CANCELLED or INVENTORY_FAILED
                    OrderResponse order = gatewayClient.getOrder(orderId, token);
                    assertThat(order.status()).isIn("CANCELLED", "INVENTORY_FAILED");

                    // Available stock must remain untouched (still 2 units)
                    InventoryResponse currentStock = gatewayClient.getInventory(product.sku(), token);
                    assertThat(currentStock.availableQuantity()).isEqualTo(availableStock);

                    // Downstream payment should NOT be captured (either 404 or not CAPTURED)
                    Response payResp = gatewayClient.getPaymentByOrderIdRaw(orderId, token);
                    if (payResp.statusCode() == 200) {
                        PaymentResponse payment = payResp.as(PaymentResponse.class);
                        assertThat(payment.status()).isNotEqualTo("CAPTURED");
                    } else {
                        assertThat(payResp.statusCode()).isEqualTo(404);
                    }

                    // Downstream shipment must NOT be created
                    Response shipResp = gatewayClient.getShipmentByOrderIdRaw(orderId, token);
                    assertThat(shipResp.statusCode()).isEqualTo(404);
                });

        log.info("Saga Compensation correctly aborted order without side effects for Order ID: {}", orderId);
    }
}
