package com.dgl.gateway.controller;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.net.URI;
import java.time.Instant;

@RestController
@RequestMapping("/fallback")
public class FallbackController {

    @RequestMapping("/product")
    public ResponseEntity<ProblemDetail> productFallback() {
        return buildFallbackResponse("Product Service", "https://api.commerce.com/errors/product-service-unavailable");
    }

    @RequestMapping("/order")
    public ResponseEntity<ProblemDetail> orderFallback() {
        return buildFallbackResponse("Order Service", "https://api.commerce.com/errors/order-service-unavailable");
    }

    @RequestMapping("/payment")
    public ResponseEntity<ProblemDetail> paymentFallback() {
        return buildFallbackResponse("Payment Service", "https://api.commerce.com/errors/payment-service-unavailable");
    }

    @RequestMapping("/inventory")
    public ResponseEntity<ProblemDetail> inventoryFallback() {
        return buildFallbackResponse("Inventory Service", "https://api.commerce.com/errors/inventory-service-unavailable");
    }

    @RequestMapping("/shipping")
    public ResponseEntity<ProblemDetail> shippingFallback() {
        return buildFallbackResponse("Shipping Service", "https://api.commerce.com/errors/shipping-service-unavailable");
    }

    @RequestMapping("/customer")
    public ResponseEntity<ProblemDetail> customerFallback() {
        return buildFallbackResponse("Customer Service", "https://api.commerce.com/errors/customer-service-unavailable");
    }

    @RequestMapping("/notification")
    public ResponseEntity<ProblemDetail> notificationFallback() {
        return buildFallbackResponse("Notification Service", "https://api.commerce.com/errors/notification-service-unavailable");
    }

    @RequestMapping("/default")
    public ResponseEntity<ProblemDetail> defaultFallback() {
        return buildFallbackResponse("Downstream Service", "https://api.commerce.com/errors/downstream-service-unavailable");
    }

    private ResponseEntity<ProblemDetail> buildFallbackResponse(String serviceName, String typeUri) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.SERVICE_UNAVAILABLE,
                serviceName + " is currently unavailable or experiencing high latency. Circuit breaker is active."
        );
        problem.setTitle("Service Temporarily Unavailable");
        problem.setType(URI.create(typeUri));
        problem.setProperty("timestamp", Instant.now());
        problem.setProperty("service", serviceName);
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(problem);
    }
}
