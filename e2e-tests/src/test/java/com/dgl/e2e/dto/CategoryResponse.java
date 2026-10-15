package com.dgl.e2e.dto;

import java.util.UUID;

public record CategoryResponse(
        UUID id,
        String name,
        String slug,
        String description
) {}
