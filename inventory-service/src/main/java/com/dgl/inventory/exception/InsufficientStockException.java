package com.dgl.inventory.exception;

import lombok.Getter;

@Getter
public class InsufficientStockException extends BusinessRuleException {

    private final String sku;
    private final int requested;
    private final int available;

    public InsufficientStockException(String sku, int requested, int available) {
        super(String.format("Insufficient stock for SKU '%s': requested %d, available %d", sku, requested, available));
        this.sku = sku;
        this.requested = requested;
        this.available = available;
    }

    public InsufficientStockException(String message) {
        super(message);
        this.sku = null;
        this.requested = 0;
        this.available = 0;
    }
}
