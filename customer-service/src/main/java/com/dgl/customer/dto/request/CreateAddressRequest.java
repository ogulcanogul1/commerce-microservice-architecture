package com.dgl.customer.dto.request;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateAddressRequest(
    @NotBlank(message = "Address title is required")
    @Size(max = 50, message = "Title cannot exceed 50 characters")
    String title,

    @NotBlank(message = "Address line 1 is required")
    @Size(max = 255, message = "Address line 1 cannot exceed 255 characters")
    String addressLine1,

    @Size(max = 255, message = "Address line 2 cannot exceed 255 characters")
    String addressLine2,

    @NotBlank(message = "City is required")
    @Size(max = 100, message = "City cannot exceed 100 characters")
    String city,

    @NotBlank(message = "District is required")
    @Size(max = 100, message = "District cannot exceed 100 characters")
    String district,

    @NotBlank(message = "Postal code is required")
    @Size(max = 20, message = "Postal code cannot exceed 20 characters")
    String postalCode,

    String country,

    boolean isDefault
) {}
