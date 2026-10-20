package com.dgl.payment.cqrs.handler.command;

import com.dgl.payment.cqrs.CommandHandler;
import com.dgl.payment.cqrs.command.ProcessPaymentCommand;
import com.dgl.payment.cqrs.mapper.PaymentResponseMapper;
import com.dgl.payment.domain.Payment;
import com.dgl.payment.domain.PaymentStatus;
import com.dgl.payment.dto.request.ProcessPaymentRequest;
import com.dgl.payment.dto.response.PaymentResponse;
import com.dgl.payment.exception.PaymentFailedException;
import com.dgl.payment.messaging.event.PaymentAuthorizedPayload;
import com.dgl.payment.outbox.OutboxService;
import com.dgl.payment.repository.PaymentRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.UUID;

@Slf4j
@Component
@RequiredArgsConstructor
public class ProcessPaymentCommandHandler implements CommandHandler<ProcessPaymentCommand, PaymentResponse> {

    private final PaymentRepository paymentRepository;
    private final OutboxService outboxService;
    private final PaymentResponseMapper paymentResponseMapper;

    @Override
    @Transactional
    public PaymentResponse handle(ProcessPaymentCommand command) {
        String idempotencyKey = command.idempotencyKey();
        ProcessPaymentRequest request = command.request();

        if (idempotencyKey != null && !idempotencyKey.isBlank()) {
            var existing = paymentRepository.findByIdempotencyKey(idempotencyKey);
            if (existing.isPresent()) {
                log.info("Idempotent hit for payment with key: {}", idempotencyKey);
                return paymentResponseMapper.toResponse(existing.get());
            }
        }

        if (request.amount() != null && request.amount().compareTo(new BigDecimal("50000.00")) >= 0) {
            log.warn("Payment authorization declined for orderId {}: Amount {} exceeds credit limit", request.orderId(), request.amount());
            throw new PaymentFailedException("Bank declined transaction: INSUFFICIENT_FUNDS (Credit limit exceeded)");
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

        outboxService.recordEvent(
                "Payment",
                saved.getId().toString(),
                "PaymentAuthorized",
                null,
                null,
                new PaymentAuthorizedPayload(
                        saved.getId(),
                        saved.getOrderId(),
                        saved.getCustomerId(),
                        saved.getAmount(),
                        saved.getCurrency(),
                        saved.getTransactionReference()
                )
        );

        log.info("Payment processed successfully via CQRS: id={}, orderId={}, txnRef={}",
                saved.getId(), saved.getOrderId(), saved.getTransactionReference());
        return paymentResponseMapper.toResponse(saved);
    }
}
