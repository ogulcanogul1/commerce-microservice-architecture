package com.dgl.e2e.scenarios;

import com.dgl.e2e.base.BaseE2ETest;
import com.dgl.e2e.dto.*;
import com.dgl.e2e.fixture.TestFixtures;
import io.restassured.response.Response;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

@DisplayName("E2E Scenario 5: High Concurrency & Zero Overselling Protection")
class ConcurrentStockDepletionE2ETest extends BaseE2ETest {

    @Test
    @DisplayName("Should prevent overselling when multiple concurrent users race for limited stock")
    void shouldPreventOversellingUnderHighConcurrency() throws InterruptedException {
        // 1. Register & Authenticate Customer
        AuthResponse auth = gatewayClient.register(TestFixtures.createRegisterRequest());
        String token = auth.accessToken();
        UUID customerId = auth.customer().id();

        // 2. Create Category & Product
        CategoryResponse category = gatewayClient.createCategory(TestFixtures.createCategoryRequest(), token);
        CreateProductRequest productReq = TestFixtures.createProductRequest(category.id());
        ProductResponse product = gatewayClient.createProduct(productReq, token);

        // 3. Provision EXACTLY 2 units of stock
        int exactAvailableStock = 2;
        gatewayClient.addStock(TestFixtures.createAddStockRequest(product.sku(), exactAvailableStock), token);

        InventoryResponse stockBefore = gatewayClient.getInventory(product.sku(), token);
        assertThat(stockBefore.availableQuantity()).isEqualTo(exactAvailableStock);

        // 4. Concurrently submit 6 orders for 1 unit each (Race Condition)
        int totalConcurrentUsers = 6;
        ExecutorService executor = Executors.newFixedThreadPool(totalConcurrentUsers);
        CountDownLatch startLatch = new CountDownLatch(1);
        CountDownLatch finishLatch = new CountDownLatch(totalConcurrentUsers);

        List<UUID> submittedOrderIds = Collections.synchronizedList(new ArrayList<>());
        AtomicInteger successfulHttpSubmissions = new AtomicInteger(0);

        for (int i = 0; i < totalConcurrentUsers; i++) {
            executor.submit(() -> {
                try {
                    startLatch.await(); // Ensure all threads start simultaneously

                    CreateOrderRequest orderReq = TestFixtures.createOrderRequest(
                            customerId,
                            product.sku(),
                            product.name(),
                            new BigDecimal("500.00"),
                            1
                    );
                    Response response = gatewayClient.createOrderRaw(orderReq, token, UUID.randomUUID().toString());
                    if (response.statusCode() == 201) {
                        successfulHttpSubmissions.incrementAndGet();
                        OrderResponse order = response.as(OrderResponse.class);
                        submittedOrderIds.add(order.id());
                    }
                } catch (Exception e) {
                    log.error("Concurrent order execution failed: {}", e.getMessage());
                } finally {
                    finishLatch.countDown();
                }
            });
        }

        // Release all threads simultaneously
        startLatch.countDown();
        boolean completedInTime = finishLatch.await(30, TimeUnit.SECONDS);
        executor.shutdown();

        assertThat(completedInTime).isTrue();
        assertThat(submittedOrderIds).isNotEmpty();
        log.info("Concurrent submissions completed: {} orders created out of {} attempts",
                submittedOrderIds.size(), totalConcurrentUsers);

        // 5. Asynchronous Saga & Inventory Verification
        await()
                .atMost(defaultTimeout())
                .pollInterval(pollInterval())
                .untilAsserted(() -> {
                    // Count CONFIRMED vs CANCELLED orders
                    int confirmedCount = 0;
                    int cancelledCount = 0;

                    for (UUID orderId : submittedOrderIds) {
                        OrderResponse order = gatewayClient.getOrder(orderId, token);
                        if ("CONFIRMED".equalsIgnoreCase(order.status())) {
                            confirmedCount++;
                        } else if ("CANCELLED".equalsIgnoreCase(order.status()) || "INVENTORY_FAILED".equalsIgnoreCase(order.status())) {
                            cancelledCount++;
                        }
                    }

                    // Strict Invariant: Exactly 'exactAvailableStock' (2) orders can be CONFIRMED!
                    assertThat(confirmedCount).isEqualTo(exactAvailableStock);
                    assertThat(cancelledCount).isEqualTo(submittedOrderIds.size() - exactAvailableStock);

                    // Final stock must NEVER be negative (No Overselling!)
                    InventoryResponse finalStock = gatewayClient.getInventory(product.sku(), token);
                    assertThat(finalStock.availableQuantity()).isEqualTo(0);
                });

        log.info("Zero Overselling Verified: exactly 2 orders CONFIRMED, remainder CANCELLED, available stock = 0");
    }
}
