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

@DisplayName("E2E Scenario 3: Idempotent Order Submission and Duplicate Message Handling")
class IdempotentOrderSubmissionE2ETest extends BaseE2ETest {

    @Test
    @DisplayName("Should return identical response and avoid duplicate deductions when request is repeated with same Idempotency-Key")
    void shouldHandleDuplicateOrderSubmissionIdempotently() {
        // 1. Register & Authenticate Customer
        AuthResponse auth = gatewayClient.register(TestFixtures.createRegisterRequest());
        String token = auth.accessToken();
        UUID customerId = auth.customer().id();

        // 2. Create Category & Product
        CategoryResponse category = gatewayClient.createCategory(TestFixtures.createCategoryRequest(), token);
        CreateProductRequest productReq = TestFixtures.createProductRequest(category.id());
        ProductResponse product = gatewayClient.createProduct(productReq, token);

        // 3. Add Stock
        int initialStock = 20;
        gatewayClient.addStock(TestFixtures.createAddStockRequest(product.sku(), initialStock), token);

        // 4. Submit First Order with unique Idempotency Key
        String sharedIdempotencyKey = "idemp-key-" + UUID.randomUUID();
        CreateOrderRequest orderReq = TestFixtures.createOrderRequest(
                customerId,
                product.sku(),
                product.name(),
                new BigDecimal("1500.00"),
                2
        );

        Response firstResp = gatewayClient.createOrderRaw(orderReq, token, sharedIdempotencyKey);
        assertThat(firstResp.statusCode()).isIn(200, 201);
        OrderResponse firstOrder = firstResp.as(OrderResponse.class);
        UUID firstOrderId = firstOrder.id();

        // 5. Submit Duplicate Order with SAME Idempotency Key (simulating client network retry)
        Response secondResp = gatewayClient.createOrderRaw(orderReq, token, sharedIdempotencyKey);
        assertThat(secondResp.statusCode()).isIn(200, 201);
        OrderResponse secondOrder = secondResp.as(OrderResponse.class);

        // Both responses must match the same order ID
        assertThat(secondOrder.id()).isEqualTo(firstOrderId);
        log.info("Idempotent retry returned matching order: id={}", firstOrderId);

        // 6. Verify stock was decremented exactly ONCE (by 2, not by 4)
        await()
                .atMost(defaultTimeout())
                .pollInterval(pollInterval())
                .untilAsserted(() -> {
                    InventoryResponse currentStock = gatewayClient.getInventory(product.sku(), token);
                    assertThat(currentStock.availableQuantity()).isEqualTo(initialStock - 2);
                });

        log.info("Idempotency verified: exactly one order processed and stock decremented once.");
    }
}
