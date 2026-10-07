package com.dgl.payment.service;

import com.dgl.payment.domain.Payment;
import com.dgl.payment.domain.PaymentRefund;
import com.dgl.payment.domain.PaymentStatus;
import com.dgl.payment.domain.RefundStatus;
import com.dgl.payment.dto.request.ProcessPaymentRequest;
import com.dgl.payment.dto.request.RefundPaymentRequest;
import com.dgl.payment.dto.response.PaymentRefundResponse;
import com.dgl.payment.dto.response.PaymentResponse;
import com.dgl.payment.exception.PaymentFailedException;
import com.dgl.payment.exception.PaymentNotFoundException;
import com.dgl.payment.repository.PaymentRefundRepository;
import com.dgl.payment.repository.PaymentRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class PaymentServiceImpl implements PaymentService {

    private final PaymentRepository paymentRepository;
    private final PaymentRefundRepository paymentRefundRepository;

    @Override
    @Transactional
    public PaymentResponse processPayment(ProcessPaymentRequest request, String idempotencyKey) {
        if (idempotencyKey != null && !idempotencyKey.isBlank()) {
            var existing = paymentRepository.findByIdempotencyKey(idempotencyKey);
            if (existing.isPresent()) {
                return mapToResponse(existing.get());
            }
        }

        String transactionReference = "TXN-" + UUID.randomUUID().toString().substring(0, 8).toUpperCase();

        Payment payment = Payment.builder()
                .orderId(request.orderId())
                .customerId(request.customerId())
                .amount(request.amount())
                .currency(request.currency() != null ? request.currency() : "TRY")
                .paymentMethod(request.paymentMethod())
                .transactionReference(transactionReference)
                .idempotencyKey(idempotencyKey)
                .status(PaymentStatus.AUTHORIZED)
                .refunds(new ArrayList<>())
                .build();

        Payment saved = paymentRepository.save(payment);
        return mapToResponse(saved);
    }

    @Override
    public PaymentResponse getPaymentById(UUID id) {
        Payment payment = paymentRepository.findById(id)
                .orElseThrow(() -> new PaymentNotFoundException(id));
        return mapToResponse(payment);
    }

    @Override
    public PaymentResponse getPaymentByOrderId(UUID orderId) {
        Payment payment = paymentRepository.findByOrderId(orderId)
                .orElseThrow(() -> new PaymentNotFoundException("Payment not found for order: " + orderId));
        return mapToResponse(payment);
    }

    @Override
    public Page<PaymentResponse> getPaymentsByCustomer(UUID customerId, Pageable pageable) {
        return paymentRepository.findByCustomerId(customerId, pageable)
                .map(this::mapToResponse);
    }

    @Override
    @Transactional
    public PaymentRefundResponse refundPayment(UUID id, RefundPaymentRequest request) {
        Payment payment = paymentRepository.findById(id)
                .orElseThrow(() -> new PaymentNotFoundException(id));

        if (payment.getStatus() == PaymentStatus.FAILED) {
            throw new PaymentFailedException("Cannot refund a failed payment");
        }

        BigDecimal alreadyRefunded = payment.getRefunds().stream()
                .filter(r -> r.getStatus() == RefundStatus.COMPLETED)
                .map(PaymentRefund::getAmount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        BigDecimal remainingRefundable = payment.getAmount().subtract(alreadyRefunded);
        if (request.amount().compareTo(remainingRefundable) > 0) {
            throw new PaymentFailedException(String.format(
                    "Requested refund amount %s exceeds refundable amount %s",
                    request.amount(), remainingRefundable));
        }

        String refundReference = "REF-" + UUID.randomUUID().toString().substring(0, 8).toUpperCase();

        PaymentRefund refund = PaymentRefund.builder()
                .payment(payment)
                .amount(request.amount())
                .refundReason(request.reason())
                .refundReference(refundReference)
                .status(RefundStatus.COMPLETED)
                .build();

        payment.getRefunds().add(refund);

        BigDecimal totalRefunded = alreadyRefunded.add(request.amount());
        if (totalRefunded.compareTo(payment.getAmount()) >= 0) {
            payment.setStatus(PaymentStatus.REFUNDED);
        }

        PaymentRefund savedRefund = paymentRefundRepository.save(refund);
        return mapRefundToResponse(savedRefund);
    }

    private PaymentResponse mapToResponse(Payment payment) {
        List<PaymentRefundResponse> refundResponses = payment.getRefunds() != null
                ? payment.getRefunds().stream().map(this::mapRefundToResponse).toList()
                : Collections.emptyList();

        return new PaymentResponse(
                payment.getId(),
                payment.getOrderId(),
                payment.getCustomerId(),
                payment.getAmount(),
                payment.getCurrency(),
                payment.getStatus(),
                payment.getPaymentMethod(),
                payment.getTransactionReference(),
                payment.getIdempotencyKey(),
                payment.getFailureReason(),
                refundResponses,
                payment.getCreatedAt(),
                payment.getUpdatedAt()
        );
    }

    private PaymentRefundResponse mapRefundToResponse(PaymentRefund refund) {
        return new PaymentRefundResponse(
                refund.getId(),
                refund.getAmount(),
                refund.getRefundReason(),
                refund.getRefundReference(),
                refund.getStatus(),
                refund.getCreatedAt()
        );
    }
}
