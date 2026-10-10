package com.dgl.order.cqrs.handler.query;

import com.dgl.order.cqrs.QueryHandler;
import com.dgl.order.cqrs.mapper.OrderResponseMapper;
import com.dgl.order.cqrs.query.GetOrderByIdQuery;
import com.dgl.order.domain.Order;
import com.dgl.order.dto.response.OrderResponse;
import com.dgl.order.exception.OrderNotFoundException;
import com.dgl.order.repository.OrderRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Slf4j
@Component
@RequiredArgsConstructor
public class GetOrderByIdQueryHandler implements QueryHandler<GetOrderByIdQuery, OrderResponse> {

    private final OrderRepository orderRepository;
    private final OrderResponseMapper orderResponseMapper;

    @Override
    @Transactional(readOnly = true)
    public OrderResponse handle(GetOrderByIdQuery query) {
        log.debug("Executing GetOrderByIdQuery for orderId: {}", query.orderId());
        Order order = orderRepository.findById(query.orderId())
                .orElseThrow(() -> new OrderNotFoundException(query.orderId()));
        return orderResponseMapper.toResponse(order);
    }
}
