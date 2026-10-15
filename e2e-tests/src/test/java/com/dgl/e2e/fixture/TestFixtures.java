package com.dgl.e2e.fixture;

import com.dgl.e2e.dto.*;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

public final class TestFixtures {

    private TestFixtures() {}

    public static String randomSuffix() {
        return UUID.randomUUID().toString().substring(0, 8);
    }

    public static RegisterRequest createRegisterRequest() {
        String suffix = randomSuffix();
        return new RegisterRequest(
                "e2e_user_" + suffix + "@commerce.test",
                "Password123!",
                "E2E",
                "Tester",
                "+90555" + suffix.replaceAll("[^0-9]", "0")
        );
    }

    public static CreateCategoryRequest createCategoryRequest() {
        String suffix = randomSuffix();
        return new CreateCategoryRequest(
                "Category " + suffix,
                "E2E Automated Test Category"
        );
    }

    public static CreateProductRequest createProductRequest(UUID categoryId) {
        String suffix = randomSuffix();
        return new CreateProductRequest(
                "SKU-E2E-" + suffix,
                "Test Product " + suffix,
                "High performance test gadget",
                categoryId,
                new BigDecimal("1500.00"),
                "TRY"
        );
    }

    public static AddStockRequest createAddStockRequest(String sku, int quantity) {
        return new AddStockRequest(sku, quantity);
    }

    public static CreateOrderRequest createOrderRequest(UUID customerId, String sku, String productName, BigDecimal unitPrice, int quantity) {
        CreateOrderItemRequest item = new CreateOrderItemRequest(sku, productName, unitPrice, quantity);
        return new CreateOrderRequest(
                customerId,
                List.of(item),
                "Ataturk Bulvari No:42 Cankaya / Ankara",
                "TRY"
        );
    }
}
