package com.dgl.e2e.dto;

public record RegisterRequest(
        String email,
        String password,
        String firstName,
        String lastName,
        String phoneNumber
) {}
