package com.dgl.shipping.repository;

import com.dgl.shipping.domain.ProcessedEvent;
import com.dgl.shipping.domain.ProcessedEventId;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface ProcessedEventRepository extends JpaRepository<ProcessedEvent, ProcessedEventId> {

    boolean existsById(ProcessedEventId id);
}
