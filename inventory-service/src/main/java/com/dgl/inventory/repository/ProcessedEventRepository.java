package com.dgl.inventory.repository;

import com.dgl.inventory.domain.ProcessedEvent;
import com.dgl.inventory.domain.ProcessedEventId;
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
