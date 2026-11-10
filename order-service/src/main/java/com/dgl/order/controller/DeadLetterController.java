package com.dgl.order.controller;

import com.dgl.order.domain.DeadLetterStatus;
import com.dgl.order.dto.response.DeadLetterMessageResponse;
import com.dgl.order.exception.AccessDeniedException;
import com.dgl.order.service.DeadLetterService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Arrays;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1/orders/dead-letters")
@RequiredArgsConstructor
@Tag(name = "Dead Letter Queue", description = "Endpoints for inspecting and re-driving poison pills and dead letter messages")
public class DeadLetterController {

    private final DeadLetterService deadLetterService;

    @GetMapping
    @Operation(summary = "List dead letter messages", description = "Retrieves paginated dead letter records with optional status filter (Admin only)")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "List of dead letter records"),
            @ApiResponse(responseCode = "403", description = "Access denied: only administrators may inspect the dead letter queue")
    })
    public ResponseEntity<Page<DeadLetterMessageResponse>> getDeadLetters(
            @RequestParam(required = false) DeadLetterStatus status,
            @RequestHeader(value = "X-User-Roles", required = false) String userRoles,
            @PageableDefault(size = 20) Pageable pageable) {
        enforceAdmin(userRoles);
        return ResponseEntity.ok(deadLetterService.getDeadLetters(status, pageable));
    }

    @PostMapping("/{id}/replay")
    @Operation(summary = "Replay dead letter message", description = "Re-publishes the dead letter record back to its original Kafka topic for reprocessing")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Message replayed successfully"),
            @ApiResponse(responseCode = "403", description = "Access denied: only administrators may replay dead letter records"),
            @ApiResponse(responseCode = "404", description = "Dead letter message not found")
    })
    public ResponseEntity<DeadLetterMessageResponse> replayDeadLetter(
            @PathVariable UUID id,
            @RequestHeader(value = "X-User-Roles", required = false) String userRoles) {
        enforceAdmin(userRoles);
        return ResponseEntity.ok(deadLetterService.replayDeadLetter(id));
    }

    @PostMapping("/{id}/discard")
    @Operation(summary = "Discard dead letter message", description = "Marks a dead letter message as discarded to prevent further processing")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Message discarded successfully"),
            @ApiResponse(responseCode = "403", description = "Access denied: only administrators may discard dead letter records"),
            @ApiResponse(responseCode = "404", description = "Dead letter message not found")
    })
    public ResponseEntity<DeadLetterMessageResponse> discardDeadLetter(
            @PathVariable UUID id,
            @RequestHeader(value = "X-User-Roles", required = false) String userRoles) {
        enforceAdmin(userRoles);
        return ResponseEntity.ok(deadLetterService.discardDeadLetter(id));
    }

    private void enforceAdmin(String userRoles) {
        if (!hasAdminRole(userRoles)) {
            throw new AccessDeniedException("Access denied: only administrators may manage the Dead Letter Queue");
        }
    }

    private boolean hasAdminRole(String userRoles) {
        if (userRoles == null || userRoles.isBlank()) {
            return false;
        }
        return Arrays.stream(userRoles.split(","))
                .map(String::trim)
                .anyMatch("ROLE_ADMIN"::equalsIgnoreCase);
    }
}
