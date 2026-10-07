package com.dgl.customer.dto.response;

import java.time.Instant;
import java.util.UUID;

public record AddressResponse(
    UUID id,
    UUID customerId,
    String title,
    String addressLine1,
    String addressLine2,
    String city,
    String district,
    String postalCode,
    String country,
    boolean isDefault,
    Instant createdAt,
    Instant updatedAt
) {}
