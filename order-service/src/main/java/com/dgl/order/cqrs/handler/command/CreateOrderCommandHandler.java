package com.dgl.order.cqrs.handler.command;

import com.dgl.order.config.OrderMetrics;
import com.dgl.order.cqrs.CommandHandler;
import com.dgl.order.cqrs.command.CreateOrderCommand;
import com.dgl.order.cqrs.mapper.OrderResponseMapper;
import com.dgl.order.domain.Order;
import com.dgl.order.domain.OrderItem;
import com.dgl.order.domain.OrderSagaState;
import com.dgl.order.domain.OrderStatus;
import com.dgl.order.dto.request.CreateOrderItemRequest;
import com.dgl.order.dto.request.CreateOrderRequest;
import com.dgl.order.dto.response.OrderResponse;
import com.dgl.order.messaging.event.OrderCreatedPayload;
import com.dgl.order.messaging.event.OrderItemPayload;
import com.dgl.order.outbox.OutboxService;
import com.dgl.order.repository.OrderRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

@Slf4j
@Component
@RequiredArgsConstructor
public class CreateOrderCommandHandler implements CommandHandler<CreateOrderCommand, OrderResponse> {

    private final OrderRepository orderRepository;
    private final OutboxService outboxService;
    private final OrderResponseMapper orderResponseMapper;

    @Autowired(required = false)
    private OrderMetrics orderMetrics;

    @Override
    @Transactional
    public OrderResponse handle(CreateOrderCommand command) {
        CreateOrderRequest request = command.request();
        UUID effectiveCorrelationId = command.correlationId() != null ? command.correlationId() : UUID.randomUUID();
        String orderNumber = "ORD-" + UUID.randomUUID().toString().substring(0, 8).toUpperCase();

        BigDecimal totalAmount = BigDecimal.ZERO;
        List<OrderItem> items = new ArrayList<>();

        Order order = Order.builder()
                .orderNumber(orderNumber)
                .customerId(request.customerId())
                .status(OrderStatus.PENDING)
                .currency(request.currency() != null ? request.currency() : "TRY")
                .shippingAddress(request.shippingAddress())
                .correlationId(effectiveCorrelationId)
                .items(items)
                .build();

        for (CreateOrderItemRequest itemReq : request.items()) {
            BigDecimal subtotal = itemReq.unitPrice().multiply(BigDecimal.valueOf(itemReq.quantity()));
            totalAmount = totalAmount.add(subtotal);

            OrderItem item = OrderItem.builder()
                    .order(order)
                    .sku(itemReq.sku())
                    .productName(itemReq.productName())
                    .unitPrice(itemReq.unitPrice())
                    .quantity(itemReq.quantity())
                    .subtotal(subtotal)
                    .build();
            items.add(item);
        }

        order.setTotalAmount(totalAmount);

        OrderSagaState sagaState = OrderSagaState.builder()
                .order(order)
                .currentStep("ORDER_CREATED")
                .build();
        order.setSagaState(sagaState);

        Order saved = orderRepository.save(order);

        List<OrderItemPayload> itemPayloads = order.getItems().stream()
                .map(i -> new OrderItemPayload(i.getSku(), i.getProductName(), i.getUnitPrice(), i.getQuantity()))
                .toList();

        OrderCreatedPayload createdPayload = new OrderCreatedPayload(
                saved.getId(),
                saved.getOrderNumber(),
                saved.getCustomerId(),
                saved.getTotalAmount(),
                saved.getCurrency(),
                saved.getShippingAddress(),
                itemPayloads
        );

        outboxService.recordEvent(
                "Order",
                saved.getId().toString(),
                "OrderCreated",
                saved.getCorrelationId(),
                null,
                createdPayload
        );

        if (orderMetrics != null) {
            orderMetrics.incrementOrdersCreated();
        }

        log.info("Order created successfully via CQRS: id={}, orderNumber={}", saved.getId(), saved.getOrderNumber());
        return orderResponseMapper.toResponse(saved);
    }
}
