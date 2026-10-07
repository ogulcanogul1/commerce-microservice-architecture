package com.dgl.payment.service;

import com.dgl.payment.dto.request.ProcessPaymentRequest;
import com.dgl.payment.dto.request.RefundPaymentRequest;
import com.dgl.payment.dto.response.PaymentRefundResponse;
import com.dgl.payment.dto.response.PaymentResponse;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

import java.util.UUID;

public interface PaymentService {

    PaymentResponse processPayment(ProcessPaymentRequest request, String idempotencyKey);

    PaymentResponse getPaymentById(UUID id);

    PaymentResponse getPaymentByOrderId(UUID orderId);

    Page<PaymentResponse> getPaymentsByCustomer(UUID customerId, Pageable pageable);

    PaymentRefundResponse refundPayment(UUID id, RefundPaymentRequest request);
}
