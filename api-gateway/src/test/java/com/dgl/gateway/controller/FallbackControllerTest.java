package com.dgl.gateway.controller;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

class FallbackControllerTest {

    private final FallbackController controller = new FallbackController();

    @Test
    @DisplayName("productFallback should return 503 SERVICE_UNAVAILABLE with ProblemDetail")
    void productFallback_ShouldReturn503() {
        ResponseEntity<ProblemDetail> response = controller.productFallback();

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().getTitle()).isEqualTo("Service Temporarily Unavailable");
        assertThat(response.getBody().getDetail()).contains("Product Service");
    }

    @Test
    @DisplayName("orderFallback should return 503 SERVICE_UNAVAILABLE with ProblemDetail")
    void orderFallback_ShouldReturn503() {
        ResponseEntity<ProblemDetail> response = controller.orderFallback();

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().getDetail()).contains("Order Service");
    }

    @Test
    @DisplayName("paymentFallback should return 503 SERVICE_UNAVAILABLE with ProblemDetail")
    void paymentFallback_ShouldReturn503() {
        ResponseEntity<ProblemDetail> response = controller.paymentFallback();

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().getDetail()).contains("Payment Service");
    }

    @Test
    @DisplayName("inventoryFallback should return 503 SERVICE_UNAVAILABLE with ProblemDetail")
    void inventoryFallback_ShouldReturn503() {
        ResponseEntity<ProblemDetail> response = controller.inventoryFallback();

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().getDetail()).contains("Inventory Service");
    }

    @Test
    @DisplayName("shippingFallback should return 503 SERVICE_UNAVAILABLE with ProblemDetail")
    void shippingFallback_ShouldReturn503() {
        ResponseEntity<ProblemDetail> response = controller.shippingFallback();

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().getDetail()).contains("Shipping Service");
    }

    @Test
    @DisplayName("customerFallback should return 503 SERVICE_UNAVAILABLE with ProblemDetail")
    void customerFallback_ShouldReturn503() {
        ResponseEntity<ProblemDetail> response = controller.customerFallback();

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().getDetail()).contains("Customer Service");
    }

    @Test
    @DisplayName("notificationFallback should return 503 SERVICE_UNAVAILABLE with ProblemDetail")
    void notificationFallback_ShouldReturn503() {
        ResponseEntity<ProblemDetail> response = controller.notificationFallback();

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().getDetail()).contains("Notification Service");
    }

    @Test
    @DisplayName("aiChatFallback should return 503 and retryable=true")
    void aiChatFallback_ShouldReturn503_WithRetryableTrue() {
        ResponseEntity<ProblemDetail> response = controller.aiChatFallback();

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().getType().toString()).isEqualTo("https://api.commerce.com/errors/ai-chat-unavailable");
        assertThat(response.getBody().getProperties()).containsEntry("retryable", true);
    }

    @Test
    @DisplayName("aiRagFallback should return 503 and retryable=true")
    void aiRagFallback_ShouldReturn503_WithRetryableTrue() {
        ResponseEntity<ProblemDetail> response = controller.aiRagFallback();

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().getType().toString()).isEqualTo("https://api.commerce.com/errors/ai-rag-unavailable");
        assertThat(response.getBody().getProperties()).containsEntry("retryable", true);
    }

    @Test
    @DisplayName("aiActionsFallback should return 503, retryable=false and outcomeUnknown=true")
    void aiActionsFallback_ShouldReturn503_WithOutcomeUnknown() {
        ResponseEntity<ProblemDetail> response = controller.aiActionsFallback();

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().getType().toString()).isEqualTo("https://api.commerce.com/errors/ai-actions-unavailable");
        assertThat(response.getBody().getProperties()).containsEntry("retryable", false);
        assertThat(response.getBody().getProperties()).containsEntry("outcomeUnknown", true);
        assertThat(response.getBody().getDetail()).contains("İşlem durumu doğrulanamadı");
    }

    @Test
    @DisplayName("aiAssistantFallback should return 503 SERVICE_UNAVAILABLE with ProblemDetail")
    void aiAssistantFallback_ShouldReturn503() {
        ResponseEntity<ProblemDetail> response = controller.aiAssistantFallback();

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().getDetail()).contains("AI Assistant Service");
    }

    @Test
    @DisplayName("defaultFallback should return 503 SERVICE_UNAVAILABLE with ProblemDetail")
    void defaultFallback_ShouldReturn503() {
        ResponseEntity<ProblemDetail> response = controller.defaultFallback();

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().getDetail()).contains("Downstream Service");
    }
}
