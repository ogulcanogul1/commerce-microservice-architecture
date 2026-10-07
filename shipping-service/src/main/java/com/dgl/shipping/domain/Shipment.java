package com.dgl.shipping.domain;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.annotations.UpdateTimestamp;
import org.hibernate.type.SqlTypes;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

@Entity
@Table(name = "shipments", indexes = {
    @Index(name = "idx_shipments_order_id", columnList = "order_id"),
    @Index(name = "idx_shipments_tracking_number", columnList = "tracking_number"),
    @Index(name = "idx_shipments_status", columnList = "status")
})
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Shipment {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "order_id", nullable = false, unique = true)
    private UUID orderId;

    @Column(name = "tracking_number", nullable = false, unique = true, length = 100)
    private String trackingNumber;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 50)
    private Carrier carrier;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 30)
    @Builder.Default
    private ShipmentStatus status = ShipmentStatus.PENDING;

    @Column(name = "recipient_name", nullable = false, length = 150)
    private String recipientName;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "delivery_address", nullable = false, columnDefinition = "jsonb")
    private String deliveryAddress;

    @Column(name = "estimated_delivery")
    private Instant estimatedDelivery;

    @Column(name = "actual_delivery")
    private Instant actualDelivery;

    @Column(name = "failure_reason", columnDefinition = "TEXT")
    private String failureReason;

    @Version
    @Column(nullable = false)
    @Builder.Default
    private Long version = 0L;

    @OneToMany(mappedBy = "shipment", cascade = CascadeType.ALL, orphanRemoval = true)
    @Builder.Default
    private List<ShipmentEvent> events = new ArrayList<>();

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @UpdateTimestamp
    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;
}
