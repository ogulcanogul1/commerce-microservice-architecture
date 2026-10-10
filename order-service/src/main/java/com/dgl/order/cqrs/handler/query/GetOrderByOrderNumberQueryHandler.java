package com.dgl.order.cqrs.handler.query;

import com.dgl.order.cqrs.QueryHandler;
import com.dgl.order.cqrs.mapper.OrderResponseMapper;
import com.dgl.order.cqrs.query.GetOrderByOrderNumberQuery;
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
public class GetOrderByOrderNumberQueryHandler implements QueryHandler<GetOrderByOrderNumberQuery, OrderResponse> {

    private final OrderRepository orderRepository;
    private final OrderResponseMapper orderResponseMapper;

    @Override
    @Transactional(readOnly = true)
    public OrderResponse handle(GetOrderByOrderNumberQuery query) {
        log.debug("Executing GetOrderByOrderNumberQuery for orderNumber: {}", query.orderNumber());
        Order order = orderRepository.findByOrderNumber(query.orderNumber())
                .orElseThrow(() -> new OrderNotFoundException("Order not found with number: " + query.orderNumber()));
        return orderResponseMapper.toResponse(order);
    }
}
