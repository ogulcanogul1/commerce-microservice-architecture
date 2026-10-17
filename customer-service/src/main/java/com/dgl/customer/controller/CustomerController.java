package com.dgl.customer.controller;

import com.dgl.customer.cqrs.CommandBus;
import com.dgl.customer.cqrs.QueryBus;
import com.dgl.customer.cqrs.command.CreateCustomerCommand;
import com.dgl.customer.cqrs.command.UpdateCustomerCommand;
import com.dgl.customer.cqrs.command.UpdatePreferencesCommand;
import com.dgl.customer.cqrs.query.GetAllCustomersQuery;
import com.dgl.customer.cqrs.query.GetCustomerByEmailQuery;
import com.dgl.customer.cqrs.query.GetCustomerByIdQuery;
import com.dgl.customer.dto.request.CreateCustomerRequest;
import com.dgl.customer.dto.request.UpdateCustomerRequest;
import com.dgl.customer.dto.request.UpdatePreferencesRequest;
import com.dgl.customer.dto.response.CustomerResponse;
import com.dgl.customer.dto.response.PreferencesResponse;
import com.dgl.customer.exception.AccessDeniedException;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.UUID;

@RestController
@RequestMapping("/api/v1/customers")
@RequiredArgsConstructor
@Tag(name = "Customers", description = "Endpoints for customer profiles, email lookup, address book, and user preferences")
public class CustomerController {

    private final CommandBus commandBus;
    private final QueryBus queryBus;

    @PostMapping
    @Operation(summary = "Create customer profile", description = "Creates a new customer profile record directly")
    @ApiResponses({
            @ApiResponse(responseCode = "201", description = "Customer created successfully"),
            @ApiResponse(responseCode = "400", description = "Invalid customer details"),
            @ApiResponse(responseCode = "409", description = "Email already registered")
    })
    public ResponseEntity<CustomerResponse> createCustomer(@Valid @RequestBody CreateCustomerRequest request) {
        CustomerResponse response = commandBus.execute(new CreateCustomerCommand(request));
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping("/{id}")
    @Operation(summary = "Get customer by ID", description = "Fetches customer details including preferences by UUID")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Customer found"),
            @ApiResponse(responseCode = "403", description = "Access denied: cannot access another customer's profile"),
            @ApiResponse(responseCode = "404", description = "Customer not found")
    })
    public ResponseEntity<CustomerResponse> getCustomerById(
            @PathVariable UUID id,
            @RequestHeader(value = "X-User-Id", required = false) String currentUserId,
            @RequestHeader(value = "X-User-Roles", required = false) String userRoles) {
        enforceOwnership(id, currentUserId, userRoles);
        return ResponseEntity.ok(queryBus.execute(new GetCustomerByIdQuery(id)));
    }

    @GetMapping("/by-email")
    @Operation(summary = "Get customer by email", description = "Fetches customer details by email address")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Customer found"),
            @ApiResponse(responseCode = "403", description = "Access denied: cannot access another customer's profile"),
            @ApiResponse(responseCode = "404", description = "Customer not found")
    })
    public ResponseEntity<CustomerResponse> getCustomerByEmail(
            @RequestParam String email,
            @RequestHeader(value = "X-User-Id", required = false) String currentUserId,
            @RequestHeader(value = "X-User-Roles", required = false) String userRoles) {
        CustomerResponse customer = queryBus.execute(new GetCustomerByEmailQuery(email));
        enforceOwnership(customer.id(), currentUserId, userRoles);
        return ResponseEntity.ok(customer);
    }

    @GetMapping
    @Operation(summary = "List all customers", description = "Retrieves paginated list of registered customers (admin only)")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "List of customers"),
            @ApiResponse(responseCode = "403", description = "Access denied: only administrators may list all customers")
    })
    public ResponseEntity<Page<CustomerResponse>> getAllCustomers(
            @RequestHeader(value = "X-User-Id", required = false) String currentUserId,
            @RequestHeader(value = "X-User-Roles", required = false) String userRoles,
            @PageableDefault(size = 20) Pageable pageable) {
        if (currentUserId != null && !currentUserId.isBlank()) {
            boolean isAdmin = userRoles != null && userRoles.contains("ROLE_ADMIN");
            if (!isAdmin) {
                throw new AccessDeniedException("Access denied: only administrators may list all customer profiles");
            }
        }
        return ResponseEntity.ok(queryBus.execute(new GetAllCustomersQuery(pageable)));
    }

    @PutMapping("/{id}")
    @Operation(summary = "Update customer profile", description = "Updates personal details (name, phone) of a customer")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Profile updated"),
            @ApiResponse(responseCode = "403", description = "Access denied: cannot modify another customer's profile"),
            @ApiResponse(responseCode = "404", description = "Customer not found")
    })
    public ResponseEntity<CustomerResponse> updateCustomer(
            @PathVariable UUID id,
            @RequestHeader(value = "X-User-Id", required = false) String currentUserId,
            @RequestHeader(value = "X-User-Roles", required = false) String userRoles,
            @Valid @RequestBody UpdateCustomerRequest request) {
        enforceOwnership(id, currentUserId, userRoles);
        return ResponseEntity.ok(commandBus.execute(new UpdateCustomerCommand(id, request)));
    }

    @PutMapping("/{id}/preferences")
    @Operation(summary = "Update customer preferences", description = "Configures marketing, notification, and language preferences")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Preferences updated"),
            @ApiResponse(responseCode = "403", description = "Access denied: cannot modify another customer's preferences"),
            @ApiResponse(responseCode = "404", description = "Customer not found")
    })
    public ResponseEntity<PreferencesResponse> updatePreferences(
            @PathVariable UUID id,
            @RequestHeader(value = "X-User-Id", required = false) String currentUserId,
            @RequestHeader(value = "X-User-Roles", required = false) String userRoles,
            @Valid @RequestBody UpdatePreferencesRequest request) {
        enforceOwnership(id, currentUserId, userRoles);
        return ResponseEntity.ok(commandBus.execute(new UpdatePreferencesCommand(id, request)));
    }

    private void enforceOwnership(UUID resourceOwnerId, String currentUserId, String userRoles) {
        if (currentUserId == null || currentUserId.isBlank() || resourceOwnerId == null) {
            return;
        }
        boolean isAdmin = userRoles != null && userRoles.contains("ROLE_ADMIN");
        if (!isAdmin && !currentUserId.equalsIgnoreCase(resourceOwnerId.toString())) {
            throw new AccessDeniedException("Access denied: you do not have permission to view or modify this customer profile");
        }
    }
}
