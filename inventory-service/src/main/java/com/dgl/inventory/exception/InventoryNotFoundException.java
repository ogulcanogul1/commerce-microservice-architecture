package com.dgl.inventory.exception;

public class InventoryNotFoundException extends BusinessRuleException {

    public InventoryNotFoundException(String sku) {
        super("Inventory not found for SKU: " + sku);
    }
}
