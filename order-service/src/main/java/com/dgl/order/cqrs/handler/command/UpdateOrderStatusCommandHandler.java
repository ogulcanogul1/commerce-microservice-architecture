package com.dgl.order.cqrs.handler.command;

import com.dgl.order.cqrs.CommandHandler;
import com.dgl.order.cqrs.command.UpdateOrderStatusCommand;
import com.dgl.order.cqrs.mapper.OrderResponseMapper;
import com.dgl.order.domain.Order;
import com.dgl.order.domain.OrderStatus;
import com.dgl.order.dto.response.OrderResponse;
import com.dgl.order.exception.OrderNotFoundException;
import com.dgl.order.messaging.event.OrderCancelledPayload;
import com.dgl.order.messaging.event.OrderConfirmedPayload;
import com.dgl.order.outbox.OutboxService;
import com.dgl.order.repository.OrderRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Slf4j
@Component
@RequiredArgsConstructor
public class UpdateOrderStatusCommandHandler implements CommandHandler<UpdateOrderStatusCommand, OrderResponse> {

    private final OrderRepository orderRepository;
    private final OutboxService outboxService;
    private final OrderResponseMapper orderResponseMapper;

    @Override
    @Transactional
    public OrderResponse handle(UpdateOrderStatusCommand command) {
        Order order = orderRepository.findById(command.orderId())
                .orElseThrow(() -> new OrderNotFoundException(command.orderId()));

        OrderStatus newStatus = command.status();
        String failureReason = command.failureReason();

        order.setStatus(newStatus);
        if (failureReason != null) {
            order.setFailureReason(failureReason);
        }

        if (newStatus == OrderStatus.CONFIRMED) {
            outboxService.recordEvent(
                    "Order",
                    order.getId().toString(),
                    "OrderConfirmed",
                    order.getCorrelationId(),
                    null,
                    new OrderConfirmedPayload(order.getId(), order.getOrderNumber(), order.getCustomerId(), order.getTotalAmount())
            );
        } else if (newStatus == OrderStatus.CANCELLED) {
            outboxService.recordEvent(
                    "Order",
                    order.getId().toString(),
                    "OrderCancelled",
                    order.getCorrelationId(),
                    null,
                    new OrderCancelledPayload(order.getId(), order.getOrderNumber(), failureReason != null ? failureReason : "Order cancelled")
            );
        }

        log.info("Order status updated via CQRS: id={}, status={}", order.getId(), newStatus);
        return orderResponseMapper.toResponse(order);
    }
}
