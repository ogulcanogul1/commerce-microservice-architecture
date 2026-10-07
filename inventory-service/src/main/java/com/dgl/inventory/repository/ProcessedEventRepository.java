package com.dgl.inventory.repository;

import com.dgl.inventory.domain.ProcessedEvent;
import com.dgl.inventory.domain.ProcessedEventId;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface ProcessedEventRepository extends JpaRepository<ProcessedEvent, ProcessedEventId> {

    boolean existsById(ProcessedEventId id);
}
