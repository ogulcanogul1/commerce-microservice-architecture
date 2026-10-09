package com.dgl.gateway.ratelimit;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Service;

import java.util.Collections;
import java.util.List;

/**
 * Distributed rate limiter service backed by Redis and executed via an atomic Lua script.
 * Employs a fail-open degradation strategy: if Redis becomes unavailable, requests are permitted.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class RateLimiterService {

    private final StringRedisTemplate redisTemplate;

    private static final String LUA_SCRIPT =
            "local key = KEYS[1] " +
            "local limit = tonumber(ARGV[1]) " +
            "local window = tonumber(ARGV[2]) " +
            "local current = redis.call('INCR', key) " +
            "if current == 1 then " +
            "    redis.call('EXPIRE', key, window) " +
            "end " +
            "local ttl = redis.call('TTL', key) " +
            "if ttl < 0 then ttl = window end " +
            "return { current, ttl }";

    @SuppressWarnings("rawtypes")
    private final DefaultRedisScript<List> redisScript = new DefaultRedisScript<>(LUA_SCRIPT, List.class);

    @SuppressWarnings("unchecked")
    public RateLimitResult tryConsume(String key, long limit, long windowSeconds) {
        String redisKey = "rate_limit:" + key;
        try {
            List<Long> result = redisTemplate.execute(
                    redisScript,
                    Collections.singletonList(redisKey),
                    String.valueOf(limit),
                    String.valueOf(windowSeconds)
            );

            if (result != null && result.size() >= 2) {
                long current = ((Number) result.get(0)).longValue();
                long ttl = ((Number) result.get(1)).longValue();
                boolean allowed = current <= limit;
                long remaining = Math.max(0, limit - current);
                return new RateLimitResult(allowed, limit, remaining, ttl);
            }
        } catch (Exception ex) {
            log.warn("Redis rate limiter unavailable for key [{}]: {}. Degrading to fail-open.", redisKey, ex.getMessage());
            return new RateLimitResult(true, limit, limit, 0);
        }
        return new RateLimitResult(true, limit, limit, 0);
    }
}
