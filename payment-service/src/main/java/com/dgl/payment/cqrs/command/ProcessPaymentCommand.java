package com.dgl.payment.cqrs.command;

import com.dgl.payment.cqrs.Command;
import com.dgl.payment.dto.request.ProcessPaymentRequest;
import com.dgl.payment.dto.response.PaymentResponse;

public record ProcessPaymentCommand(
        ProcessPaymentRequest request,
        String idempotencyKey
) implements Command<PaymentResponse> {
}
