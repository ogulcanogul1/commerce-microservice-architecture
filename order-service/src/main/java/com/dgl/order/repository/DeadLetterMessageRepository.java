package com.dgl.order.repository;

import com.dgl.order.domain.DeadLetterMessage;
import com.dgl.order.domain.DeadLetterStatus;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.UUID;

@Repository
public interface DeadLetterMessageRepository extends JpaRepository<DeadLetterMessage, UUID> {

    Page<DeadLetterMessage> findByStatus(DeadLetterStatus status, Pageable pageable);
}
