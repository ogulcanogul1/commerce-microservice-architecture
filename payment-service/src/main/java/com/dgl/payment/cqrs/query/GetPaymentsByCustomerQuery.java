package com.dgl.payment.cqrs.query;

import com.dgl.payment.cqrs.Query;
import com.dgl.payment.dto.response.PaymentResponse;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

import java.util.UUID;

public record GetPaymentsByCustomerQuery(
        UUID customerId,
        Pageable pageable
) implements Query<Page<PaymentResponse>> {
}
