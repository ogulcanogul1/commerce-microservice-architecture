package com.dgl.inventory.exception;

public class InsufficientStockException extends RuntimeException {

    public InsufficientStockException(String sku, int requested, int available) {
        super(String.format("Insufficient stock for SKU '%s': requested %d, available %d", sku, requested, available));
    }

    public InsufficientStockException(String message) {
        super(message);
    }
}
