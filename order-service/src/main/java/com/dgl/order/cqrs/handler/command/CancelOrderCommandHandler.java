package com.dgl.order.cqrs.handler.command;

import com.dgl.order.cqrs.CommandHandler;
import com.dgl.order.cqrs.command.CancelOrderCommand;
import com.dgl.order.cqrs.mapper.OrderResponseMapper;
import com.dgl.order.domain.Order;
import com.dgl.order.domain.OrderStatus;
import com.dgl.order.dto.request.CancelOrderRequest;
import com.dgl.order.dto.response.OrderResponse;
import com.dgl.order.exception.InvalidOrderStateException;
import com.dgl.order.exception.OrderNotFoundException;
import com.dgl.order.messaging.event.OrderCancelledPayload;
import com.dgl.order.outbox.OutboxService;
import com.dgl.order.repository.OrderRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Slf4j
@Component
@RequiredArgsConstructor
public class CancelOrderCommandHandler implements CommandHandler<CancelOrderCommand, OrderResponse> {

    private final OrderRepository orderRepository;
    private final OutboxService outboxService;
    private final OrderResponseMapper orderResponseMapper;

    @Override
    @Transactional
    public OrderResponse handle(CancelOrderCommand command) {
        Order order = orderRepository.findById(command.orderId())
                .orElseThrow(() -> new OrderNotFoundException(command.orderId()));

        if (order.getStatus() == OrderStatus.CANCELLED) {
            return orderResponseMapper.toResponse(order);
        }

        if (order.getStatus() == OrderStatus.CONFIRMED) {
            throw new InvalidOrderStateException("Confirmed order cannot be cancelled directly via standard cancel endpoint");
        }

        CancelOrderRequest request = command.request();
        order.setStatus(OrderStatus.CANCELLED);
        order.setFailureReason(request.reason());

        if (order.getSagaState() != null) {
            order.getSagaState().setFailureStep(order.getSagaState().getCurrentStep());
            order.getSagaState().setFailureReason(request.reason());
            order.getSagaState().setCurrentStep("ORDER_CANCELLED");
        }

        outboxService.recordEvent(
                "Order",
                order.getId().toString(),
                "OrderCancelled",
                order.getCorrelationId(),
                null,
                new OrderCancelledPayload(order.getId(), order.getOrderNumber(), request.reason())
        );

        log.info("Order cancelled via CQRS: id={}, reason={}", order.getId(), request.reason());
        return orderResponseMapper.toResponse(order);
    }
}
