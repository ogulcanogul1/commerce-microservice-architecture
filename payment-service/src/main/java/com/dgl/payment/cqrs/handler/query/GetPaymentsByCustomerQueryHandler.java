package com.dgl.payment.cqrs.handler.query;

import com.dgl.payment.cqrs.QueryHandler;
import com.dgl.payment.cqrs.mapper.PaymentResponseMapper;
import com.dgl.payment.cqrs.query.GetPaymentsByCustomerQuery;
import com.dgl.payment.dto.response.PaymentResponse;
import com.dgl.payment.repository.PaymentRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Slf4j
@Component
@RequiredArgsConstructor
public class GetPaymentsByCustomerQueryHandler implements QueryHandler<GetPaymentsByCustomerQuery, Page<PaymentResponse>> {

    private final PaymentRepository paymentRepository;
    private final PaymentResponseMapper paymentResponseMapper;

    @Override
    @Transactional(readOnly = true)
    public Page<PaymentResponse> handle(GetPaymentsByCustomerQuery query) {
        log.debug("Executing GetPaymentsByCustomerQuery for customerId: {}", query.customerId());
        return paymentRepository.findByCustomerId(query.customerId(), query.pageable())
                .map(paymentResponseMapper::toResponse);
    }
}
