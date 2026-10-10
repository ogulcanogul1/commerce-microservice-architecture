package com.dgl.order.cqrs.handler.command;

import com.dgl.order.config.OrderMetrics;
import com.dgl.order.cqrs.CommandHandler;
import com.dgl.order.cqrs.command.HandlePaymentAuthorizedCommand;
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
public class HandlePaymentAuthorizedCommandHandler implements CommandHandler<HandlePaymentAuthorizedCommand, Void> {

    private final OrderRepository orderRepository;
    private final OutboxService outboxService;

    @Autowired(required = false)
    private OrderMetrics orderMetrics;

    @Override
    @Transactional
    public Void handle(HandlePaymentAuthorizedCommand command) {
        UUID orderId = command.orderId();
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        if (order.getStatus() == OrderStatus.CANCELLED) {
            log.info("Order {} already cancelled, ignoring payment authorized event", orderId);
            return null;
        }

        OrderSagaState saga = order.getSagaState();
        if (saga != null) {
            saga.setPaymentAuthorizedAt(Instant.now());
            if (saga.getInventoryReservedAt() != null) {
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
                log.info("Order {} confirmed after payment authorized (inventory already reserved)", orderId);
            } else {
                order.setStatus(OrderStatus.PAYMENT_AUTHORIZED);
                saga.setCurrentStep("PAYMENT_AUTHORIZED");
                log.info("Order {} transitioned to PAYMENT_AUTHORIZED", orderId);
            }
        }

        return null;
    }
}
