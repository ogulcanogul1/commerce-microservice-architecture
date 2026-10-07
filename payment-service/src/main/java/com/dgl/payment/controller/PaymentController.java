package com.dgl.payment.controller;

import com.dgl.payment.dto.request.ProcessPaymentRequest;
import com.dgl.payment.dto.request.RefundPaymentRequest;
import com.dgl.payment.dto.response.PaymentRefundResponse;
import com.dgl.payment.dto.response.PaymentResponse;
import com.dgl.payment.service.PaymentService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

@RestController
@RequestMapping("/api/v1/payments")
@RequiredArgsConstructor
public class PaymentController {

    private final PaymentService paymentService;

    @PostMapping
    public ResponseEntity<PaymentResponse> processPayment(
            @Valid @RequestBody ProcessPaymentRequest request,
            @RequestHeader(name = "Idempotency-Key", required = true) String idempotencyKey) {
        PaymentResponse response = paymentService.processPayment(request, idempotencyKey);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping("/{id}")
    public ResponseEntity<PaymentResponse> getPaymentById(@PathVariable UUID id) {
        return ResponseEntity.ok(paymentService.getPaymentById(id));
    }

    @GetMapping("/order/{orderId}")
    public ResponseEntity<PaymentResponse> getPaymentByOrderId(@PathVariable UUID orderId) {
        return ResponseEntity.ok(paymentService.getPaymentByOrderId(orderId));
    }

    @GetMapping("/customer/{customerId}")
    public ResponseEntity<Page<PaymentResponse>> getPaymentsByCustomer(
            @PathVariable UUID customerId,
            @PageableDefault(size = 20) Pageable pageable) {
        return ResponseEntity.ok(paymentService.getPaymentsByCustomer(customerId, pageable));
    }

    @PostMapping("/{id}/refund")
    public ResponseEntity<PaymentRefundResponse> refundPayment(
            @PathVariable UUID id,
            @Valid @RequestBody RefundPaymentRequest request) {
        PaymentRefundResponse response = paymentService.refundPayment(id, request);
        return ResponseEntity.ok(response);
    }
}
