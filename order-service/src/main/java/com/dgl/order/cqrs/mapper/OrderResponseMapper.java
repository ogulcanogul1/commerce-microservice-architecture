package com.dgl.order.cqrs.mapper;

import com.dgl.order.domain.Order;
import com.dgl.order.domain.OrderSagaState;
import com.dgl.order.dto.response.OrderItemResponse;
import com.dgl.order.dto.response.OrderResponse;
import com.dgl.order.dto.response.OrderSagaStateResponse;
import org.springframework.stereotype.Component;

import java.util.Collections;
import java.util.List;

/**
 * Reusable mapper component converting {@link Order} entities to {@link OrderResponse} DTOs.
 */
@Component
public class OrderResponseMapper {

    public OrderResponse toResponse(Order order) {
        if (order == null) {
            return null;
        }

        List<OrderItemResponse> itemResponses = order.getItems() != null
                ? order.getItems().stream()
                .map(item -> new OrderItemResponse(
                        item.getId(),
                        item.getSku(),
                        item.getProductName(),
                        item.getUnitPrice(),
                        item.getQuantity(),
                        item.getSubtotal()
                ))
                .toList()
                : Collections.emptyList();

        OrderSagaStateResponse sagaResponse = null;
        if (order.getSagaState() != null) {
            OrderSagaState s = order.getSagaState();
            sagaResponse = new OrderSagaStateResponse(
                    s.getCurrentStep(),
                    s.getInventoryReservedAt(),
                    s.getPaymentAuthorizedAt(),
                    s.getShippingCreatedAt(),
                    s.getFailureStep(),
                    s.getFailureReason()
            );
        }

        return new OrderResponse(
                order.getId(),
                order.getOrderNumber(),
                order.getCustomerId(),
                order.getStatus(),
                order.getTotalAmount(),
                order.getCurrency(),
                order.getShippingAddress(),
                order.getFailureReason(),
                order.getCorrelationId(),
                itemResponses,
                sagaResponse,
                order.getCreatedAt(),
                order.getUpdatedAt()
        );
    }
}
