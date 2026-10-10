package com.dgl.order.cqrs.handler.command;

import com.dgl.order.config.OrderMetrics;
import com.dgl.order.cqrs.CommandHandler;
import com.dgl.order.cqrs.command.HandleInventoryFailedCommand;
import com.dgl.order.domain.Order;
import com.dgl.order.domain.OrderSagaState;
import com.dgl.order.domain.OrderStatus;
import com.dgl.order.exception.OrderNotFoundException;
import com.dgl.order.messaging.event.OrderCancelledPayload;
import com.dgl.order.outbox.OutboxService;
import com.dgl.order.repository.OrderRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Slf4j
@Component
@RequiredArgsConstructor
public class HandleInventoryFailedCommandHandler implements CommandHandler<HandleInventoryFailedCommand, Void> {

    private final OrderRepository orderRepository;
    private final OutboxService outboxService;

    @Autowired(required = false)
    private OrderMetrics orderMetrics;

    @Override
    @Transactional
    public Void handle(HandleInventoryFailedCommand command) {
        UUID orderId = command.orderId();
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        if (order.getStatus() == OrderStatus.CANCELLED) {
            log.info("Order {} already cancelled, ignoring inventory failed", orderId);
            return null;
        }

        String finalReason = command.reason() != null ? command.reason() : "Inventory reservation failed";
        order.setStatus(OrderStatus.CANCELLED);
        order.setFailureReason(finalReason);

        OrderSagaState saga = order.getSagaState();
        if (saga != null) {
            saga.setCurrentStep("INVENTORY_FAILED");
            saga.setFailureStep("INVENTORY_RESERVED");
            saga.setFailureReason(finalReason);
        }

        outboxService.recordEvent(
                "Order",
                order.getId().toString(),
                "OrderCancelled",
                order.getCorrelationId(),
                null,
                new OrderCancelledPayload(order.getId(), order.getOrderNumber(), finalReason)
        );

        if (orderMetrics != null) {
            orderMetrics.incrementOrdersCancelled();
        }

        log.warn("Order {} cancelled due to inventory failure: {}", orderId, finalReason);
        return null;
    }
}
