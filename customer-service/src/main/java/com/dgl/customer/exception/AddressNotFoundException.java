package com.dgl.customer.exception;

import java.util.UUID;

public class AddressNotFoundException extends BusinessRuleException {

    public AddressNotFoundException(UUID id) {
        super("Address not found with ID: " + id);
    }

    public AddressNotFoundException(String message) {
        super(message);
    }
}
