package com.dgl.order.cqrs.handler.command;

import com.dgl.order.config.OrderMetrics;
import com.dgl.order.cqrs.CommandHandler;
import com.dgl.order.cqrs.command.HandleInventoryReservedCommand;
import com.dgl.order.domain.Order;
import com.dgl.order.domain.OrderSagaState;
import com.dgl.order.domain.OrderStatus;
import com.dgl.order.exception.OrderNotFoundException;
import com.dgl.order.messaging.event.OrderConfirmedPayload;
import com.dgl.order.outbox.OutboxService;
import com.dgl.order.repository.OrderRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.UUID;

@Slf4j
@Component
@RequiredArgsConstructor
public class HandleInventoryReservedCommandHandler implements CommandHandler<HandleInventoryReservedCommand, Void> {

    private final OrderRepository orderRepository;
    private final OutboxService outboxService;

    @Autowired(required = false)
    private OrderMetrics orderMetrics;

    @Override
    @Transactional
    public Void handle(HandleInventoryReservedCommand command) {
        UUID orderId = command.orderId();
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        if (order.getStatus() == OrderStatus.CANCELLED) {
            log.info("Order {} is already cancelled, ignoring inventory reserved event", orderId);
            return null;
        }

        OrderSagaState saga = order.getSagaState();
        if (saga != null) {
            saga.setInventoryReservedAt(Instant.now());
            if (saga.getPaymentAuthorizedAt() != null) {
                // Both inventory and payment succeeded -> Order Confirmed!
                order.setStatus(OrderStatus.CONFIRMED);
                saga.setCurrentStep("CONFIRMED");
                outboxService.recordEvent(
                        "Order",
                        order.getId().toString(),
                        "OrderConfirmed",
                        order.getCorrelationId(),
                        null,
                        new OrderConfirmedPayload(order.getId(), order.getOrderNumber(), order.getCustomerId(), order.getTotalAmount())
                );
                if (orderMetrics != null) {
                    orderMetrics.incrementOrdersConfirmed();
                }
                log.info("Order {} confirmed after inventory reserved (payment already authorized)", orderId);
            } else {
                order.setStatus(OrderStatus.INVENTORY_RESERVED);
                saga.setCurrentStep("INVENTORY_RESERVED");
                log.info("Order {} transitioned to INVENTORY_RESERVED", orderId);
            }
        }

        return null;
    }
}
