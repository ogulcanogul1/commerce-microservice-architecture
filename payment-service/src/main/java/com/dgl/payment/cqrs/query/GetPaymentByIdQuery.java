package com.dgl.payment.cqrs.query;

import com.dgl.payment.cqrs.Query;
import com.dgl.payment.dto.response.PaymentResponse;

import java.util.UUID;

public record GetPaymentByIdQuery(UUID id) implements Query<PaymentResponse> {
}
