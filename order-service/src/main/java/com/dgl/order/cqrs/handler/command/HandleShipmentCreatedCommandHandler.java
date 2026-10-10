package com.dgl.order.cqrs.handler.command;

import com.dgl.order.cqrs.CommandHandler;
import com.dgl.order.cqrs.command.HandleShipmentCreatedCommand;
import com.dgl.order.domain.Order;
import com.dgl.order.domain.OrderSagaState;
import com.dgl.order.domain.OrderStatus;
import com.dgl.order.exception.OrderNotFoundException;
import com.dgl.order.repository.OrderRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.UUID;

@Slf4j
@Component
@RequiredArgsConstructor
public class HandleShipmentCreatedCommandHandler implements CommandHandler<HandleShipmentCreatedCommand, Void> {

    private final OrderRepository orderRepository;

    @Override
    @Transactional
    public Void handle(HandleShipmentCreatedCommand command) {
        UUID orderId = command.orderId();
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        OrderSagaState saga = order.getSagaState();
        if (saga != null) {
            saga.setShippingCreatedAt(Instant.now());
            saga.setCurrentStep("SHIPPING_CREATED");
        }
        order.setStatus(OrderStatus.SHIPPING_CREATED);

        log.info("Order {} transitioned to SHIPPING_CREATED", orderId);
        return null;
    }
}
