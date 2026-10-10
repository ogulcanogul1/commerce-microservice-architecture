package com.dgl.payment.service;

import com.dgl.payment.cqrs.CommandBus;
import com.dgl.payment.cqrs.QueryBus;
import com.dgl.payment.cqrs.command.ProcessPaymentCommand;
import com.dgl.payment.cqrs.command.RefundPaymentCommand;
import com.dgl.payment.cqrs.query.GetPaymentByIdQuery;
import com.dgl.payment.cqrs.query.GetPaymentByOrderIdQuery;
import com.dgl.payment.cqrs.query.GetPaymentsByCustomerQuery;
import com.dgl.payment.dto.request.ProcessPaymentRequest;
import com.dgl.payment.dto.request.RefundPaymentRequest;
import com.dgl.payment.dto.response.PaymentRefundResponse;
import com.dgl.payment.dto.response.PaymentResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;

import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class PaymentServiceImpl implements PaymentService {

    private final CommandBus commandBus;
    private final QueryBus queryBus;

    @Override
    public PaymentResponse processPayment(ProcessPaymentRequest request, String idempotencyKey) {
        return commandBus.execute(new ProcessPaymentCommand(request, idempotencyKey));
    }

    @Override
    public PaymentResponse getPaymentById(UUID id) {
        return queryBus.execute(new GetPaymentByIdQuery(id));
    }

    @Override
    public PaymentResponse getPaymentByOrderId(UUID orderId) {
        return queryBus.execute(new GetPaymentByOrderIdQuery(orderId));
    }

    @Override
    public Page<PaymentResponse> getPaymentsByCustomer(UUID customerId, Pageable pageable) {
        return queryBus.execute(new GetPaymentsByCustomerQuery(customerId, pageable));
    }

    @Override
    public PaymentRefundResponse refundPayment(UUID id, RefundPaymentRequest request) {
        return commandBus.execute(new RefundPaymentCommand(id, request));
    }
}
