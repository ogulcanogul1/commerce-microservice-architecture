package com.dgl.e2e.dto;

import java.util.UUID;

public record CreateCategoryRequest(
        String name,
        String description
) {}
