package com.dgl.shipping.service;

import com.dgl.shipping.dto.request.CreateShipmentRequest;
import com.dgl.shipping.dto.request.UpdateShipmentStatusRequest;
import com.dgl.shipping.dto.response.ShipmentResponse;
import com.dgl.shipping.dto.response.TrackingResponse;

import java.util.UUID;

public interface ShippingService {

    ShipmentResponse createShipment(CreateShipmentRequest request);

    ShipmentResponse getShipmentById(UUID id);

    ShipmentResponse getShipmentByOrderId(UUID orderId);

    TrackingResponse trackShipment(String trackingNumber);

    ShipmentResponse updateShipmentStatus(UUID id, UpdateShipmentStatusRequest request);

    ShipmentResponse cancelShipment(UUID id, String reason);
}
