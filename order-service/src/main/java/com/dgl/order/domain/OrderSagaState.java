package com.dgl.order.domain;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "order_saga_states")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class OrderSagaState {

    @Id
    @Column(name = "order_id")
    private UUID orderId;

    @OneToOne(fetch = FetchType.LAZY)
    @MapsId
    @JoinColumn(name = "order_id")
    private Order order;

    @Column(name = "current_step", nullable = false, length = 50)
    private String currentStep;

    @Column(name = "inventory_reserved_at")
    private Instant inventoryReservedAt;

    @Column(name = "payment_authorized_at")
    private Instant paymentAuthorizedAt;

    @Column(name = "shipping_created_at")
    private Instant shippingCreatedAt;

    @Column(name = "failure_step", length = 50)
    private String failureStep;

    @Column(name = "failure_reason", columnDefinition = "TEXT")
    private String failureReason;

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @UpdateTimestamp
    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;
}
