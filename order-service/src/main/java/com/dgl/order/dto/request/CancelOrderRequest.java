package com.dgl.order.dto.request;

import jakarta.validation.constraints.NotBlank;

public record CancelOrderRequest(
    @NotBlank(message = "Cancel reason is required")
    String reason
) {}
