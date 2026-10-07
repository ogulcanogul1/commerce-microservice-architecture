package com.dgl.payment.service;

import com.dgl.payment.domain.IdempotencyRecord;

import java.util.Optional;

public interface IdempotencyService {

    Optional<IdempotencyRecord> findRecord(String idempotencyKey);

    IdempotencyRecord startProcessing(String idempotencyKey, String requestHash);

    void completeProcessing(String idempotencyKey, String responsePayload);

    void failProcessing(String idempotencyKey);
}
