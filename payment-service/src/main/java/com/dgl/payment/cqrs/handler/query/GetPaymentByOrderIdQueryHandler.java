package com.dgl.payment.cqrs.handler.query;

import com.dgl.payment.cqrs.QueryHandler;
import com.dgl.payment.cqrs.mapper.PaymentResponseMapper;
import com.dgl.payment.cqrs.query.GetPaymentByOrderIdQuery;
import com.dgl.payment.domain.Payment;
import com.dgl.payment.dto.response.PaymentResponse;
import com.dgl.payment.exception.PaymentNotFoundException;
import com.dgl.payment.repository.PaymentRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Slf4j
@Component
@RequiredArgsConstructor
public class GetPaymentByOrderIdQueryHandler implements QueryHandler<GetPaymentByOrderIdQuery, PaymentResponse> {

    private final PaymentRepository paymentRepository;
    private final PaymentResponseMapper paymentResponseMapper;

    @Override
    @Transactional(readOnly = true)
    public PaymentResponse handle(GetPaymentByOrderIdQuery query) {
        log.debug("Executing GetPaymentByOrderIdQuery for orderId: {}", query.orderId());
        Payment payment = paymentRepository.findByOrderId(query.orderId())
                .orElseThrow(() -> new PaymentNotFoundException("Payment not found for order: " + query.orderId()));
        return paymentResponseMapper.toResponse(payment);
    }
}
