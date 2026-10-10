package com.dgl.order.cqrs.handler.command;

import com.dgl.order.config.OrderMetrics;
import com.dgl.order.cqrs.CommandHandler;
import com.dgl.order.cqrs.command.HandleSagaTimeoutCommand;
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
public class HandleSagaTimeoutCommandHandler implements CommandHandler<HandleSagaTimeoutCommand, Void> {

    private final OrderRepository orderRepository;
    private final OutboxService outboxService;

    @Autowired(required = false)
    private OrderMetrics orderMetrics;

    @Override
    @Transactional
    public Void handle(HandleSagaTimeoutCommand command) {
        UUID orderId = command.orderId();
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        if (order.getStatus() == OrderStatus.CANCELLED || order.getStatus() == OrderStatus.CONFIRMED) {
            log.info("Order {} already in terminal state {}, skipping timeout cancellation", order.getId(), order.getStatus());
            return null;
        }

        String timeoutReason = "Saga execution timed out after waiting for intermediate step completion";
        order.setStatus(OrderStatus.CANCELLED);
        order.setFailureReason(timeoutReason);

        OrderSagaState saga = order.getSagaState();
        if (saga != null) {
            saga.setFailureStep(saga.getCurrentStep());
            saga.setFailureReason(timeoutReason);
            saga.setCurrentStep("SAGA_TIMEOUT");
        }

        outboxService.recordEvent(
                "Order",
                order.getId().toString(),
                "OrderCancelled",
                order.getCorrelationId(),
                null,
                new OrderCancelledPayload(order.getId(), order.getOrderNumber(), timeoutReason)
        );

        if (orderMetrics != null) {
            orderMetrics.incrementOrdersCancelled();
            orderMetrics.incrementSagaTimeouts();
        }

        log.warn("Order {} (number={}) timed out during saga execution and was cancelled via CQRS. Compensation event emitted.",
                order.getId(), order.getOrderNumber());
        return null;
    }
}
