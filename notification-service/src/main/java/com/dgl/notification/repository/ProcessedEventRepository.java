package com.dgl.notification.repository;

import com.dgl.notification.domain.ProcessedEvent;
import com.dgl.notification.domain.ProcessedEventId;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.stereotype.Repository;

import java.time.Instant;

@Repository
public interface ProcessedEventRepository extends JpaRepository<ProcessedEvent, ProcessedEventId> {

    boolean existsById(ProcessedEventId id);

    @Modifying
    int deleteByProcessedAtBefore(Instant cutoff);
}
