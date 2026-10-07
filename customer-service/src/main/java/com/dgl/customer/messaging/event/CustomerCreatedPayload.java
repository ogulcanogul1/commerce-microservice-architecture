package com.dgl.customer.messaging.event;

import java.util.UUID;

public record CustomerCreatedPayload(
    UUID customerId,
    String email,
    String firstName,
    String lastName,
    String phoneNumber,
    String status
) {}
