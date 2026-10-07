package com.dgl.customer.dto.request;

import com.dgl.customer.domain.CustomerStatus;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record UpdateCustomerRequest(
    @NotBlank(message = "First name is required")
    @Size(max = 100, message = "First name cannot exceed 100 characters")
    String firstName,

    @NotBlank(message = "Last name is required")
    @Size(max = 100, message = "Last name cannot exceed 100 characters")
    String lastName,

    @Size(max = 30, message = "Phone number cannot exceed 30 characters")
    String phoneNumber,

    CustomerStatus status
) {}
