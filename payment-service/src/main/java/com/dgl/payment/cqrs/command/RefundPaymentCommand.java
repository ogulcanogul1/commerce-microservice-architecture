package com.dgl.payment.cqrs.command;

import com.dgl.payment.cqrs.Command;
import com.dgl.payment.dto.request.RefundPaymentRequest;
import com.dgl.payment.dto.response.PaymentRefundResponse;

import java.util.UUID;

public record RefundPaymentCommand(
        UUID id,
        RefundPaymentRequest request
) implements Command<PaymentRefundResponse> {
}
