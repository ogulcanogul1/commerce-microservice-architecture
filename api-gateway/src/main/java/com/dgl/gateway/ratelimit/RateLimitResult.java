package com.dgl.gateway.ratelimit;

public record RateLimitResult(
        boolean allowed,
        long limit,
        long remaining,
        long resetSeconds
) {}
