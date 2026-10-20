package com.dgl.payment.cqrs.handler.command;

import com.dgl.payment.cqrs.command.ProcessPaymentCommand;
import com.dgl.payment.cqrs.command.RefundPaymentCommand;
import com.dgl.payment.cqrs.mapper.PaymentResponseMapper;
import com.dgl.payment.domain.Payment;
import com.dgl.payment.domain.PaymentRefund;
import com.dgl.payment.domain.PaymentStatus;
import com.dgl.payment.dto.request.ProcessPaymentRequest;
import com.dgl.payment.dto.request.RefundPaymentRequest;
import com.dgl.payment.dto.response.PaymentRefundResponse;
import com.dgl.payment.dto.response.PaymentResponse;
import com.dgl.payment.exception.PaymentFailedException;
import com.dgl.payment.outbox.OutboxService;
import com.dgl.payment.repository.PaymentRefundRepository;
import com.dgl.payment.repository.PaymentRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
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
class PaymentCommandHandlerTest {

    @Mock
    private PaymentRepository paymentRepository;

    @Mock
    private PaymentRefundRepository paymentRefundRepository;

    @Mock
    private OutboxService outboxService;

    private final PaymentResponseMapper mapper = new PaymentResponseMapper();

    private ProcessPaymentCommandHandler processHandler;
    private RefundPaymentCommandHandler refundHandler;

    private UUID orderId;
    private UUID customerId;
    private UUID paymentId;
    private Payment samplePayment;

    @BeforeEach
    void setUp() {
        processHandler = new ProcessPaymentCommandHandler(paymentRepository, outboxService, mapper);
        refundHandler = new RefundPaymentCommandHandler(paymentRepository, paymentRefundRepository, outboxService, mapper);

        orderId = UUID.randomUUID();
        customerId = UUID.randomUUID();
        paymentId = UUID.randomUUID();

        samplePayment = Payment.builder()
                .id(paymentId)
                .orderId(orderId)
                .customerId(customerId)
                .amount(new BigDecimal("100.00"))
                .currency("TRY")
                .paymentMethod("CREDIT_CARD")
                .transactionReference("TXN-12345678")
                .status(PaymentStatus.AUTHORIZED)
                .refunds(new ArrayList<>())
                .build();
    }

    @Test
    @DisplayName("ProcessPayment: Should persist payment and emit PaymentAuthorized event")
    void processPayment_shouldSucceed() {
        ProcessPaymentRequest request = new ProcessPaymentRequest(
                orderId, customerId, new BigDecimal("100.00"), "TRY", "CREDIT_CARD"
        );

        when(paymentRepository.findByIdempotencyKey("KEY-1")).thenReturn(Optional.empty());
        when(paymentRepository.save(any(Payment.class))).thenReturn(samplePayment);

        PaymentResponse response = processHandler.handle(new ProcessPaymentCommand(request, "KEY-1"));

        assertThat(response).isNotNull();
        assertThat(response.amount()).isEqualByComparingTo(new BigDecimal("100.00"));
        verify(outboxService).recordEvent(eq("Payment"), eq(paymentId.toString()), eq("PaymentAuthorized"), isNull(), isNull(), any());
    }

    @Test
    @DisplayName("ProcessPayment: Should throw PaymentFailedException when amount exceeds credit limit")
    void processPayment_exceedsCreditLimit_shouldThrowPaymentFailedException() {
        ProcessPaymentRequest request = new ProcessPaymentRequest(
                orderId, customerId, new BigDecimal("60000.00"), "TRY", "CREDIT_CARD"
        );

        when(paymentRepository.findByIdempotencyKey(any())).thenReturn(Optional.empty());

        assertThatThrownBy(() -> processHandler.handle(new ProcessPaymentCommand(request, "KEY-LIMIT-EXCEEDED")))
                .isInstanceOf(PaymentFailedException.class)
                .hasMessageContaining("INSUFFICIENT_FUNDS");

        verify(paymentRepository, never()).save(any());
        verify(outboxService, never()).recordEvent(any(), any(), any(), any(), any(), any());
    }

    @Test
    @DisplayName("ProcessPayment: Idempotent key should return existing payment")
    void processPayment_idempotentHit_shouldReturnExisting() {
        ProcessPaymentRequest request = new ProcessPaymentRequest(
                orderId, customerId, new BigDecimal("100.00"), "TRY", "CREDIT_CARD"
        );

        when(paymentRepository.findByIdempotencyKey("KEY-1")).thenReturn(Optional.of(samplePayment));

        PaymentResponse response = processHandler.handle(new ProcessPaymentCommand(request, "KEY-1"));

        assertThat(response).isNotNull();
        verify(paymentRepository, never()).save(any());
        verify(outboxService, never()).recordEvent(any(), any(), any(), any(), any(), any());
    }

    @Test
    @DisplayName("RefundPayment: Should refund and emit PaymentRefunded event")
    void refundPayment_shouldSucceed() {
        RefundPaymentRequest request = new RefundPaymentRequest(new BigDecimal("50.00"), "Customer request");

        when(paymentRepository.findById(paymentId)).thenReturn(Optional.of(samplePayment));
        when(paymentRefundRepository.save(any(PaymentRefund.class))).thenAnswer(i -> i.getArgument(0));

        PaymentRefundResponse response = refundHandler.handle(new RefundPaymentCommand(paymentId, request));

        assertThat(response).isNotNull();
        assertThat(response.amount()).isEqualByComparingTo(new BigDecimal("50.00"));
        verify(outboxService).recordEvent(eq("Payment"), eq(paymentId.toString()), eq("PaymentRefunded"), isNull(), isNull(), any());
    }

    @Test
    @DisplayName("RefundPayment: Exceeding amount should throw PaymentFailedException")
    void refundPayment_exceedingAmount_shouldThrowException() {
        RefundPaymentRequest request = new RefundPaymentRequest(new BigDecimal("150.00"), "Too much");

        when(paymentRepository.findById(paymentId)).thenReturn(Optional.of(samplePayment));

        assertThatThrownBy(() -> refundHandler.handle(new RefundPaymentCommand(paymentId, request)))
                .isInstanceOf(PaymentFailedException.class)
                .hasMessageContaining("exceeds refundable amount");
    }
}
