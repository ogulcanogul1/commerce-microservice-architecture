package com.dgl.inventory.repository;

import com.dgl.inventory.domain.ReservationStatus;
import com.dgl.inventory.domain.StockReservation;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Repository
public interface StockReservationRepository extends JpaRepository<StockReservation, UUID> {

    List<StockReservation> findByOrderId(UUID orderId);

    List<StockReservation> findByStatusAndExpiresAtBefore(ReservationStatus status, Instant now);
}
