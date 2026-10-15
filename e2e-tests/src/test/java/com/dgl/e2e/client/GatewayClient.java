package com.dgl.e2e.client;

import com.dgl.e2e.dto.*;
import io.restassured.RestAssured;
import io.restassured.http.ContentType;
import io.restassured.response.Response;
import io.restassured.specification.RequestSpecification;

import java.util.List;
import java.util.UUID;

public class GatewayClient {

    private final String baseUrl;

    public GatewayClient(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    private RequestSpecification request() {
        return RestAssured.given()
                .baseUri(baseUrl)
                .contentType(ContentType.JSON)
                .accept(ContentType.JSON);
    }

    private RequestSpecification authRequest(String token) {
        RequestSpecification req = request();
        if (token != null && !token.isBlank()) {
            req.header("Authorization", "Bearer " + token);
        }
        return req;
    }

    public Response getHealth() {
        return request()
                .when()
                .get("/actuator/health");
    }

    public AuthResponse register(RegisterRequest request) {
        return request()
                .body(request)
                .when()
                .post("/api/v1/auth/register")
                .then()
                .statusCode(201)
                .extract()
                .as(AuthResponse.class);
    }

    public CategoryResponse createCategory(CreateCategoryRequest request, String token) {
        return authRequest(token)
                .body(request)
                .when()
                .post("/api/v1/categories")
                .then()
                .statusCode(201)
                .extract()
                .as(CategoryResponse.class);
    }

    public ProductResponse createProduct(CreateProductRequest request, String token) {
        return authRequest(token)
                .body(request)
                .when()
                .post("/api/v1/products")
                .then()
                .statusCode(201)
                .extract()
                .as(ProductResponse.class);
    }

    public InventoryResponse addStock(AddStockRequest request, String token) {
        return authRequest(token)
                .body(request)
                .when()
                .post("/api/v1/inventory/stock")
                .then()
                .statusCode(201)
                .extract()
                .as(InventoryResponse.class);
    }

    public InventoryResponse getInventory(String sku, String token) {
        return authRequest(token)
                .when()
                .get("/api/v1/inventory/" + sku)
                .then()
                .statusCode(200)
                .extract()
                .as(InventoryResponse.class);
    }

    public Response createOrderRaw(CreateOrderRequest request, String token, String idempotencyKey) {
        RequestSpecification spec = authRequest(token).body(request);
        if (idempotencyKey != null && !idempotencyKey.isBlank()) {
            spec.header("Idempotency-Key", idempotencyKey);
        }
        return spec.when().post("/api/v1/orders");
    }

    public OrderResponse createOrder(CreateOrderRequest request, String token, String idempotencyKey) {
        return createOrderRaw(request, token, idempotencyKey)
                .then()
                .statusCode(201)
                .extract()
                .as(OrderResponse.class);
    }

    public OrderResponse getOrder(UUID orderId, String token) {
        return authRequest(token)
                .when()
                .get("/api/v1/orders/" + orderId)
                .then()
                .statusCode(200)
                .extract()
                .as(OrderResponse.class);
    }

    public Response getOrderRaw(UUID orderId, String token) {
        return authRequest(token)
                .when()
                .get("/api/v1/orders/" + orderId);
    }

    public Response getPaymentByOrderIdRaw(UUID orderId, String token) {
        return authRequest(token)
                .when()
                .get("/api/v1/payments/order/" + orderId);
    }

    public PaymentResponse getPaymentByOrderId(UUID orderId, String token) {
        return getPaymentByOrderIdRaw(orderId, token)
                .then()
                .statusCode(200)
                .extract()
                .as(PaymentResponse.class);
    }

    public Response getShipmentByOrderIdRaw(UUID orderId, String token) {
        return authRequest(token)
                .when()
                .get("/api/v1/shipments/order/" + orderId);
    }

    public ShipmentResponse getShipmentByOrderId(UUID orderId, String token) {
        return getShipmentByOrderIdRaw(orderId, token)
                .then()
                .statusCode(200)
                .extract()
                .as(ShipmentResponse.class);
    }

    public List<NotificationResponse> getNotificationsByCustomerId(UUID customerId, String token) {
        return authRequest(token)
                .when()
                .get("/api/v1/notifications/customer/" + customerId)
                .then()
                .statusCode(200)
                .extract()
                .jsonPath()
                .getList(".", NotificationResponse.class);
    }
}
