package com.dgl.shipping.dto.request;

import com.dgl.shipping.domain.Carrier;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.util.UUID;

public record CreateShipmentRequest(
    @NotNull(message = "Order ID is required")
    UUID orderId,

    @NotNull(message = "Carrier is required")
    Carrier carrier,

    @NotBlank(message = "Recipient name is required")
    String recipientName,

    @NotBlank(message = "Delivery address is required")
    String deliveryAddress
) {}
