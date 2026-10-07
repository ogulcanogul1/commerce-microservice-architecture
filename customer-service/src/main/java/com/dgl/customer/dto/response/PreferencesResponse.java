package com.dgl.customer.dto.response;

import java.time.Instant;
import java.util.UUID;

public record PreferencesResponse(
    UUID customerId,
    boolean emailNotifications,
    boolean smsNotifications,
    boolean pushNotifications,
    String language,
    String currency,
    Instant updatedAt
) {}
