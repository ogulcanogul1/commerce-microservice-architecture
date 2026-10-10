package com.dgl.payment.cqrs.handler.command;

import com.dgl.payment.cqrs.CommandHandler;
import com.dgl.payment.cqrs.command.RefundPaymentCommand;
import com.dgl.payment.cqrs.mapper.PaymentResponseMapper;
import com.dgl.payment.domain.Payment;
import com.dgl.payment.domain.PaymentRefund;
import com.dgl.payment.domain.PaymentStatus;
import com.dgl.payment.domain.RefundStatus;
import com.dgl.payment.dto.request.RefundPaymentRequest;
import com.dgl.payment.dto.response.PaymentRefundResponse;
import com.dgl.payment.exception.PaymentFailedException;
import com.dgl.payment.exception.PaymentNotFoundException;
import com.dgl.payment.messaging.event.PaymentRefundedPayload;
import com.dgl.payment.outbox.OutboxService;
import com.dgl.payment.repository.PaymentRefundRepository;
import com.dgl.payment.repository.PaymentRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.UUID;

@Slf4j
@Component
@RequiredArgsConstructor
public class RefundPaymentCommandHandler implements CommandHandler<RefundPaymentCommand, PaymentRefundResponse> {

    private final PaymentRepository paymentRepository;
    private final PaymentRefundRepository paymentRefundRepository;
    private final OutboxService outboxService;
    private final PaymentResponseMapper paymentResponseMapper;

    @Override
    @Transactional
    public PaymentRefundResponse handle(RefundPaymentCommand command) {
        UUID id = command.id();
        RefundPaymentRequest request = command.request();

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

        outboxService.recordEvent(
                "Payment",
                payment.getId().toString(),
                "PaymentRefunded",
                null,
                null,
                new PaymentRefundedPayload(
                        payment.getId(),
                        payment.getOrderId(),
                        savedRefund.getAmount(),
                        savedRefund.getRefundReference(),
                        savedRefund.getRefundReason()
                )
        );

        log.info("Payment refunded successfully via CQRS: paymentId={}, refundRef={}", payment.getId(), refundReference);
        return paymentResponseMapper.toRefundResponse(savedRefund);
    }
}
