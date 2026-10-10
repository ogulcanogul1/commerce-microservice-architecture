package com.dgl.payment.cqrs.handler.query;

import com.dgl.payment.cqrs.QueryHandler;
import com.dgl.payment.cqrs.mapper.PaymentResponseMapper;
import com.dgl.payment.cqrs.query.GetPaymentByIdQuery;
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
public class GetPaymentByIdQueryHandler implements QueryHandler<GetPaymentByIdQuery, PaymentResponse> {

    private final PaymentRepository paymentRepository;
    private final PaymentResponseMapper paymentResponseMapper;

    @Override
    @Transactional(readOnly = true)
    public PaymentResponse handle(GetPaymentByIdQuery query) {
        log.debug("Executing GetPaymentByIdQuery for id: {}", query.id());
        Payment payment = paymentRepository.findById(query.id())
                .orElseThrow(() -> new PaymentNotFoundException(query.id()));
        return paymentResponseMapper.toResponse(payment);
    }
}
