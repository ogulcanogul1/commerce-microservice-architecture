package com.dgl.e2e.dto;

public record AddStockRequest(
        String sku,
        int quantity
) {}
