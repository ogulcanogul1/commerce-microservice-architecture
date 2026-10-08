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
import com.dgl.payment.messaging.event.PaymentAuthorizedPayload;
import com.dgl.payment.messaging.event.PaymentRefundedPayload;
import com.dgl.payment.outbox.OutboxService;
import com.dgl.payment.repository.PaymentRefundRepository;
import com.dgl.payment.repository.PaymentRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class PaymentServiceImplTest {

    @Mock
    private PaymentRepository paymentRepository;

    @Mock
    private PaymentRefundRepository paymentRefundRepository;

    @Mock
    private OutboxService outboxService;

    @InjectMocks
    private PaymentServiceImpl paymentService;

    private UUID paymentId;
    private UUID orderId;
    private UUID customerId;
    private Payment samplePayment;

    @BeforeEach
    void setUp() {
        paymentId = UUID.randomUUID();
        orderId = UUID.randomUUID();
        customerId = UUID.randomUUID();

        samplePayment = Payment.builder()
                .id(paymentId)
                .orderId(orderId)
                .customerId(customerId)
                .amount(new BigDecimal("200.00"))
                .currency("TRY")
                .paymentMethod("CREDIT_CARD")
                .transactionReference("TXN-TEST1234")
                .idempotencyKey("KEY-123")
                .status(PaymentStatus.AUTHORIZED)
                .refunds(new ArrayList<>())
                .build();
    }

    @Test
    @DisplayName("processPayment: Should authorize payment and emit PaymentAuthorized outbox event")
    void processPayment_newPayment_shouldAuthorizeAndEmitOutboxEvent() {
        when(paymentRepository.findByIdempotencyKey("KEY-123")).thenReturn(Optional.empty());
        when(paymentRepository.save(any(Payment.class))).thenAnswer(i -> {
            Payment p = i.getArgument(0);
            p.setId(paymentId);
            return p;
        });

        ProcessPaymentRequest request = new ProcessPaymentRequest(
                orderId,
                customerId,
                new BigDecimal("200.00"),
                "TRY",
                "CREDIT_CARD"
        );

        PaymentResponse response = paymentService.processPayment(request, "KEY-123");

        assertThat(response).isNotNull();
        assertThat(response.id()).isEqualTo(paymentId);
        assertThat(response.status()).isEqualTo(PaymentStatus.AUTHORIZED);
        assertThat(response.amount()).isEqualByComparingTo(new BigDecimal("200.00"));

        verify(outboxService).recordEvent(
                eq("Payment"),
                eq(paymentId.toString()),
                eq("PaymentAuthorized"),
                isNull(),
                isNull(),
                any(PaymentAuthorizedPayload.class)
        );
    }

    @Test
    @DisplayName("processPayment: Idempotent call with existing key should return existing payment without re-saving")
    void processPayment_existingIdempotencyKey_shouldReturnExisting() {
        when(paymentRepository.findByIdempotencyKey("KEY-123")).thenReturn(Optional.of(samplePayment));

        ProcessPaymentRequest request = new ProcessPaymentRequest(
                orderId,
                customerId,
                new BigDecimal("200.00"),
                "TRY",
                "CREDIT_CARD"
        );

        PaymentResponse response = paymentService.processPayment(request, "KEY-123");

        assertThat(response.id()).isEqualTo(paymentId);
        verify(paymentRepository, never()).save(any());
        verifyNoInteractions(outboxService);
    }

    @Test
    @DisplayName("refundPayment: Valid refund should record refund, mark REFUNDED and emit PaymentRefunded")
    void refundPayment_fullRefund_shouldMarkRefundedAndEmitOutboxEvent() {
        when(paymentRepository.findById(paymentId)).thenReturn(Optional.of(samplePayment));
        when(paymentRefundRepository.save(any(PaymentRefund.class))).thenAnswer(i -> {
            PaymentRefund r = i.getArgument(0);
            r.setId(UUID.randomUUID());
            return r;
        });

        RefundPaymentRequest request = new RefundPaymentRequest(new BigDecimal("200.00"), "Customer cancellation");
        PaymentRefundResponse refundResponse = paymentService.refundPayment(paymentId, request);

        assertThat(refundResponse).isNotNull();
        assertThat(refundResponse.amount()).isEqualByComparingTo(new BigDecimal("200.00"));
        assertThat(refundResponse.status()).isEqualTo(RefundStatus.COMPLETED);
        assertThat(samplePayment.getStatus()).isEqualTo(PaymentStatus.REFUNDED);

        verify(outboxService).recordEvent(
                eq("Payment"),
                eq(paymentId.toString()),
                eq("PaymentRefunded"),
                isNull(),
                isNull(),
                any(PaymentRefundedPayload.class)
        );
    }

    @Test
    @DisplayName("refundPayment: Amount exceeding remaining refundable should throw PaymentFailedException")
    void refundPayment_amountExceeding_shouldThrowException() {
        when(paymentRepository.findById(paymentId)).thenReturn(Optional.of(samplePayment));

        RefundPaymentRequest request = new RefundPaymentRequest(new BigDecimal("250.00"), "Too high");

        assertThatThrownBy(() -> paymentService.refundPayment(paymentId, request))
                .isInstanceOf(PaymentFailedException.class)
                .hasMessageContaining("exceeds refundable amount");

        verifyNoInteractions(outboxService);
    }

    @Test
    @DisplayName("refundPayment: Cannot refund a failed payment")
    void refundPayment_failedPayment_shouldThrowException() {
        samplePayment.setStatus(PaymentStatus.FAILED);
        when(paymentRepository.findById(paymentId)).thenReturn(Optional.of(samplePayment));

        RefundPaymentRequest request = new RefundPaymentRequest(new BigDecimal("100.00"), "Refund test");

        assertThatThrownBy(() -> paymentService.refundPayment(paymentId, request))
                .isInstanceOf(PaymentFailedException.class)
                .hasMessageContaining("Cannot refund a failed payment");
    }

    @Test
    @DisplayName("getPaymentById: Non-existent ID should throw PaymentNotFoundException")
    void getPaymentById_notFound_shouldThrowException() {
        UUID nonExistent = UUID.randomUUID();
        when(paymentRepository.findById(nonExistent)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> paymentService.getPaymentById(nonExistent))
                .isInstanceOf(PaymentNotFoundException.class);
    }
}
