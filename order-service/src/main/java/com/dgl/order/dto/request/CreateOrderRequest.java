package com.dgl.order.dto.request;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import java.util.List;
import java.util.UUID;

public record CreateOrderRequest(
    @NotNull(message = "Customer ID is required")
    UUID customerId,

    @NotEmpty(message = "Items cannot be empty")
    @Valid
    List<CreateOrderItemRequest> items,

    @NotBlank(message = "Shipping address is required")
    String shippingAddress,

    String currency
) {}
