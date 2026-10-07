package com.dgl.customer.dto.request;

public record UpdatePreferencesRequest(
    Boolean emailNotifications,
    Boolean smsNotifications,
    Boolean pushNotifications,
    String language,
    String currency
) {}
