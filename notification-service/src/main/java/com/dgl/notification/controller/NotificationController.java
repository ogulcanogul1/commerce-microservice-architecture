package com.dgl.notification.controller;

import com.dgl.notification.dto.request.SendNotificationRequest;
import com.dgl.notification.dto.response.NotificationResponse;
import com.dgl.notification.service.NotificationService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1/notifications")
@RequiredArgsConstructor
@Tag(name = "Notifications", description = "Endpoints for dispatching and querying multi-channel notifications")
public class NotificationController {

    private final NotificationService notificationService;

    @PostMapping
    @Operation(summary = "Send notification", description = "Dispatches a notification message via email, SMS, or push channel")
    @ApiResponses({
            @ApiResponse(responseCode = "201", description = "Notification dispatched"),
            @ApiResponse(responseCode = "400", description = "Invalid notification parameters")
    })
    public ResponseEntity<NotificationResponse> sendNotification(@Valid @RequestBody SendNotificationRequest request) {
        NotificationResponse response = notificationService.sendNotification(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping("/{id}")
    @Operation(summary = "Get notification by ID", description = "Retrieves delivery status and details by notification UUID")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Notification found"),
            @ApiResponse(responseCode = "404", description = "Notification not found")
    })
    public ResponseEntity<NotificationResponse> getNotificationById(@PathVariable UUID id) {
        return ResponseEntity.ok(notificationService.getNotificationById(id));
    }

    @GetMapping("/customer/{customerId}")
    @Operation(summary = "List customer notifications", description = "Retrieves notification history for a specific customer")
    public ResponseEntity<List<NotificationResponse>> getNotificationsByCustomer(@PathVariable UUID customerId) {
        return ResponseEntity.ok(notificationService.getNotificationsByCustomer(customerId));
    }
}
