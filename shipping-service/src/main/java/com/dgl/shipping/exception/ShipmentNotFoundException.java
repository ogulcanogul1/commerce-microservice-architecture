package com.dgl.shipping.exception;

import java.util.UUID;

public class ShipmentNotFoundException extends BusinessRuleException {

    public ShipmentNotFoundException(UUID id) {
        super("Shipment not found with ID: " + id);
    }

    public ShipmentNotFoundException(String message) {
        super(message);
    }
}
