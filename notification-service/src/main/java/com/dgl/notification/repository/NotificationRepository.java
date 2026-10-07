package com.dgl.notification.repository;

import com.dgl.notification.domain.Notification;
import com.dgl.notification.domain.NotificationStatus;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Repository
public interface NotificationRepository extends JpaRepository<Notification, UUID> {

    List<Notification> findByCustomerId(UUID customerId);

    List<Notification> findByCustomerIdOrderByCreatedAtDesc(UUID customerId);

    Optional<Notification> findByEventId(UUID eventId);

    List<Notification> findByStatus(NotificationStatus status);
}
