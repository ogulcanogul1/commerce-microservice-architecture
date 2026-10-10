package com.dgl.order.cqrs.handler.command;

import com.dgl.order.cqrs.CommandHandler;
import com.dgl.order.cqrs.command.UpdateSagaStepCommand;
import com.dgl.order.cqrs.mapper.OrderResponseMapper;
import com.dgl.order.domain.Order;
import com.dgl.order.domain.OrderSagaState;
import com.dgl.order.dto.response.OrderResponse;
import com.dgl.order.exception.OrderNotFoundException;
import com.dgl.order.repository.OrderRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;

@Slf4j
@Component
@RequiredArgsConstructor
public class UpdateSagaStepCommandHandler implements CommandHandler<UpdateSagaStepCommand, OrderResponse> {

    private final OrderRepository orderRepository;
    private final OrderResponseMapper orderResponseMapper;

    @Override
    @Transactional
    public OrderResponse handle(UpdateSagaStepCommand command) {
        Order order = orderRepository.findById(command.orderId())
                .orElseThrow(() -> new OrderNotFoundException(command.orderId()));

        order.setStatus(command.status());
        if (command.failureReason() != null) {
            order.setFailureReason(command.failureReason());
        }

        OrderSagaState saga = order.getSagaState();
        if (saga != null) {
            saga.setCurrentStep(command.step());
            Instant now = Instant.now();
            switch (command.step()) {
                case "INVENTORY_RESERVED" -> saga.setInventoryReservedAt(now);
                case "PAYMENT_AUTHORIZED" -> saga.setPaymentAuthorizedAt(now);
                case "SHIPPING_CREATED" -> saga.setShippingCreatedAt(now);
                default -> {}
            }
            if (command.failureReason() != null) {
                saga.setFailureStep(command.step());
                saga.setFailureReason(command.failureReason());
            }
        }

        log.info("Order saga step updated via CQRS: id={}, step={}, status={}", order.getId(), command.step(), command.status());
        return orderResponseMapper.toResponse(order);
    }
}
