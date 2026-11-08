package com.dgl.gateway.controller;

import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.net.URI;
import java.time.Instant;

/**
 * Gateway Circuit Breaker Fallback Controller.
 *
 * Mikroservisler zaman aşımına uğradığında veya devre kesici açık (OPEN) durumdayken
 * istemcilere standart RFC 7807 ProblemDetail yanıtları döner.
 */
@Slf4j
@RestController
@RequestMapping("/fallback")
public class FallbackController {

    @RequestMapping("/product")
    public ResponseEntity<ProblemDetail> productFallback() {
        return buildFallbackResponse("Product Service", "https://api.commerce.com/errors/product-service-unavailable", true);
    }

    @RequestMapping("/order")
    public ResponseEntity<ProblemDetail> orderFallback() {
        return buildFallbackResponse("Order Service", "https://api.commerce.com/errors/order-service-unavailable", true);
    }

    @RequestMapping("/payment")
    public ResponseEntity<ProblemDetail> paymentFallback() {
        return buildFallbackResponse("Payment Service", "https://api.commerce.com/errors/payment-service-unavailable", true);
    }

    @RequestMapping("/inventory")
    public ResponseEntity<ProblemDetail> inventoryFallback() {
        return buildFallbackResponse("Inventory Service", "https://api.commerce.com/errors/inventory-service-unavailable", true);
    }

    @RequestMapping("/shipping")
    public ResponseEntity<ProblemDetail> shippingFallback() {
        return buildFallbackResponse("Shipping Service", "https://api.commerce.com/errors/shipping-service-unavailable", true);
    }

    @RequestMapping("/customer")
    public ResponseEntity<ProblemDetail> customerFallback() {
        return buildFallbackResponse("Customer Service", "https://api.commerce.com/errors/customer-service-unavailable", true);
    }

    @RequestMapping("/notification")
    public ResponseEntity<ProblemDetail> notificationFallback() {
        return buildFallbackResponse("Notification Service", "https://api.commerce.com/errors/notification-service-unavailable", true);
    }

    // --- AI Assistant Özel Fallback Uç Noktaları ---

    @RequestMapping("/ai-chat")
    public ResponseEntity<ProblemDetail> aiChatFallback() {
        return buildFallbackResponse("AI Chat", "https://api.commerce.com/errors/ai-chat-unavailable", true);
    }

    @RequestMapping("/ai-rag")
    public ResponseEntity<ProblemDetail> aiRagFallback() {
        return buildFallbackResponse("AI RAG", "https://api.commerce.com/errors/ai-rag-unavailable", true);
    }

    @RequestMapping("/ai-actions")
    public ResponseEntity<ProblemDetail> aiActionsFallback() {
        // Aksiyon onaylarında (sipariş iptali vb.) timeout olunca tekrar deneme yapılamaz (outcomeUnknown=true)
        log.warn("Circuit breaker fallback triggered for AI Actions: outcome is unknown");
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.SERVICE_UNAVAILABLE,
                "İşlem durumu doğrulanamadı. Tekrar denemeden önce siparişlerinizi kontrol edin."
        );
        problem.setTitle("Service Temporarily Unavailable");
        problem.setType(URI.create("https://api.commerce.com/errors/ai-actions-unavailable"));
        problem.setProperty("timestamp", Instant.now());
        problem.setProperty("service", "AI Actions");
        problem.setProperty("retryable", false);
        problem.setProperty("outcomeUnknown", true);
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(problem);
    }

    @RequestMapping("/ai-assistant")
    public ResponseEntity<ProblemDetail> aiAssistantFallback() {
        return buildFallbackResponse("AI Assistant Service", "https://api.commerce.com/errors/ai-assistant-service-unavailable", true);
    }

    @RequestMapping("/default")
    public ResponseEntity<ProblemDetail> defaultFallback() {
        return buildFallbackResponse("Downstream Service", "https://api.commerce.com/errors/downstream-service-unavailable", true);
    }

    private ResponseEntity<ProblemDetail> buildFallbackResponse(String serviceName, String typeUri, boolean retryable) {
        log.warn("Circuit breaker fallback triggered for service: {}", serviceName);
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.SERVICE_UNAVAILABLE,
                serviceName + " is currently unavailable or experiencing high latency. Circuit breaker is active."
        );
        problem.setTitle("Service Temporarily Unavailable");
        problem.setType(URI.create(typeUri));
        problem.setProperty("timestamp", Instant.now());
        problem.setProperty("service", serviceName);
        problem.setProperty("retryable", retryable);
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(problem);
    }
}
