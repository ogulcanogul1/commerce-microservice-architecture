package com.dgl.payment.exception;

import java.util.UUID;

public class PaymentNotFoundException extends BusinessRuleException {

    public PaymentNotFoundException(UUID id) {
        super("Payment not found with ID: " + id);
    }

    public PaymentNotFoundException(String message) {
        super(message);
    }
}
