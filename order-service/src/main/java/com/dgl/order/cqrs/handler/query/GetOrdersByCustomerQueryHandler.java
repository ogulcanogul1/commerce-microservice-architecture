package com.dgl.order.cqrs.handler.query;

import com.dgl.order.cqrs.QueryHandler;
import com.dgl.order.cqrs.mapper.OrderResponseMapper;
import com.dgl.order.cqrs.query.GetOrdersByCustomerQuery;
import com.dgl.order.dto.response.OrderResponse;
import com.dgl.order.repository.OrderRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Slf4j
@Component
@RequiredArgsConstructor
public class GetOrdersByCustomerQueryHandler implements QueryHandler<GetOrdersByCustomerQuery, Page<OrderResponse>> {

    private final OrderRepository orderRepository;
    private final OrderResponseMapper orderResponseMapper;

    @Override
    @Transactional(readOnly = true)
    public Page<OrderResponse> handle(GetOrdersByCustomerQuery query) {
        log.debug("Executing GetOrdersByCustomerQuery for customerId: {}", query.customerId());
        return orderRepository.findByCustomerId(query.customerId(), query.pageable())
                .map(orderResponseMapper::toResponse);
    }
}
