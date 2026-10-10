package com.dgl.payment.cqrs.query;

import com.dgl.payment.cqrs.Query;
import com.dgl.payment.dto.response.PaymentResponse;

import java.util.UUID;

public record GetPaymentByOrderIdQuery(UUID orderId) implements Query<PaymentResponse> {
}
