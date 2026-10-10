package com.dgl.payment.cqrs.mapper;

import com.dgl.payment.domain.Payment;
import com.dgl.payment.domain.PaymentRefund;
import com.dgl.payment.dto.response.PaymentRefundResponse;
import com.dgl.payment.dto.response.PaymentResponse;
import org.springframework.stereotype.Component;

import java.util.Collections;
import java.util.List;

@Component
public class PaymentResponseMapper {

    public PaymentResponse toResponse(Payment payment) {
        if (payment == null) {
            return null;
        }

        List<PaymentRefundResponse> refundResponses = payment.getRefunds() != null
                ? payment.getRefunds().stream().map(this::toRefundResponse).toList()
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

    public PaymentRefundResponse toRefundResponse(PaymentRefund refund) {
        if (refund == null) {
            return null;
        }

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
