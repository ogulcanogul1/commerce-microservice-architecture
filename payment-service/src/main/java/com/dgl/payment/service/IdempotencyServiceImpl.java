package com.dgl.payment.service;

import com.dgl.payment.domain.IdempotencyRecord;
import com.dgl.payment.domain.IdempotencyStatus;
import com.dgl.payment.repository.IdempotencyRecordRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Duration;
import java.time.Instant;
import java.util.Optional;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class IdempotencyServiceImpl implements IdempotencyService {

    private static final Duration TTL = Duration.ofHours(24);

    private final IdempotencyRecordRepository idempotencyRecordRepository;

    @Override
    public Optional<IdempotencyRecord> findRecord(String idempotencyKey) {
        return idempotencyRecordRepository.findByIdempotencyKey(idempotencyKey);
    }

    @Override
    @Transactional
    public IdempotencyRecord startProcessing(String idempotencyKey, String requestHash) {
        IdempotencyRecord record = IdempotencyRecord.builder()
                .idempotencyKey(idempotencyKey)
                .requestHash(requestHash)
                .status(IdempotencyStatus.PROCESSING)
                .expiresAt(Instant.now().plus(TTL))
                .build();
        return idempotencyRecordRepository.save(record);
    }

    @Override
    @Transactional
    public void completeProcessing(String idempotencyKey, String responsePayload) {
        idempotencyRecordRepository.findByIdempotencyKey(idempotencyKey)
                .ifPresent(record -> {
                    record.setStatus(IdempotencyStatus.COMPLETED);
                    record.setResponsePayload(responsePayload);
                });
    }

    @Override
    @Transactional
    public void failProcessing(String idempotencyKey) {
        idempotencyRecordRepository.findByIdempotencyKey(idempotencyKey)
                .ifPresent(record -> record.setStatus(IdempotencyStatus.FAILED));
    }
}
