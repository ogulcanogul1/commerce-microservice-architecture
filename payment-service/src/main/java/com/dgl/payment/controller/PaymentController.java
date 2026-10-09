package com.dgl.payment.controller;

import com.dgl.payment.dto.request.ProcessPaymentRequest;
import com.dgl.payment.dto.request.RefundPaymentRequest;
import com.dgl.payment.dto.response.PaymentRefundResponse;
import com.dgl.payment.dto.response.PaymentResponse;
import com.dgl.payment.service.PaymentService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.UUID;

@RestController
@RequestMapping("/api/v1/payments")
@RequiredArgsConstructor
@Tag(name = "Payments", description = "Endpoints for processing payments, idempotent charges, and issuing refunds")
public class PaymentController {

    private final PaymentService paymentService;

    @PostMapping
    @Operation(summary = "Process payment", description = "Authorizes or captures payment with mandatory Idempotency-Key header to prevent duplicate charges")
    @ApiResponses({
            @ApiResponse(responseCode = "201", description = "Payment processed successfully"),
            @ApiResponse(responseCode = "400", description = "Validation error or invalid payment data"),
            @ApiResponse(responseCode = "409", description = "Payment declined or concurrent idempotency conflict")
    })
    public ResponseEntity<PaymentResponse> processPayment(
            @Valid @RequestBody ProcessPaymentRequest request,
            @Parameter(description = "Unique client-generated idempotency key (UUID or random string)", required = true)
            @RequestHeader(name = "Idempotency-Key", required = true) String idempotencyKey) {
        PaymentResponse response = paymentService.processPayment(request, idempotencyKey);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping("/{id}")
    @Operation(summary = "Get payment by ID", description = "Retrieves payment details by payment UUID")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Payment record found"),
            @ApiResponse(responseCode = "404", description = "Payment not found")
    })
    public ResponseEntity<PaymentResponse> getPaymentById(@PathVariable UUID id) {
        return ResponseEntity.ok(paymentService.getPaymentById(id));
    }

    @GetMapping("/order/{orderId}")
    @Operation(summary = "Get payment by Order ID", description = "Retrieves payment transaction associated with a specific order")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Payment record found"),
            @ApiResponse(responseCode = "404", description = "Payment not found")
    })
    public ResponseEntity<PaymentResponse> getPaymentByOrderId(@PathVariable UUID orderId) {
        return ResponseEntity.ok(paymentService.getPaymentByOrderId(orderId));
    }

    @GetMapping("/customer/{customerId}")
    @Operation(summary = "List customer payments", description = "Retrieves paginated history of payments made by a customer")
    public ResponseEntity<Page<PaymentResponse>> getPaymentsByCustomer(
            @PathVariable UUID customerId,
            @PageableDefault(size = 20) Pageable pageable) {
        return ResponseEntity.ok(paymentService.getPaymentsByCustomer(customerId, pageable));
    }

    @PostMapping("/{id}/refund")
    @Operation(summary = "Refund payment", description = "Initiates full or partial refund for a captured payment transaction")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Payment refunded successfully"),
            @ApiResponse(responseCode = "400", description = "Payment cannot be refunded or refund amount exceeds captured amount"),
            @ApiResponse(responseCode = "404", description = "Payment not found")
    })
    public ResponseEntity<PaymentRefundResponse> refundPayment(
            @PathVariable UUID id,
            @Valid @RequestBody RefundPaymentRequest request) {
        PaymentRefundResponse response = paymentService.refundPayment(id, request);
        return ResponseEntity.ok(response);
    }
}
