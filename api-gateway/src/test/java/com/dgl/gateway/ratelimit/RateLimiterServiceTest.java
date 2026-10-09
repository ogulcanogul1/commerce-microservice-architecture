package com.dgl.gateway.ratelimit;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class RateLimiterServiceTest {

    @Mock
    private StringRedisTemplate redisTemplate;

    @InjectMocks
    private RateLimiterService rateLimiterService;

    @Test
    @DisplayName("tryConsume: Should allow request when current counter is within limit")
    void tryConsume_shouldAllowWhenWithinLimit() {
        when(redisTemplate.execute(any(DefaultRedisScript.class), anyList(), eq("10"), eq("60")))
                .thenReturn(List.of(3L, 45L));

        RateLimitResult result = rateLimiterService.tryConsume("ip:127.0.0.1", 10, 60);

        assertThat(result.allowed()).isTrue();
        assertThat(result.limit()).isEqualTo(10);
        assertThat(result.remaining()).isEqualTo(7);
        assertThat(result.resetSeconds()).isEqualTo(45);
    }

    @Test
    @DisplayName("tryConsume: Should reject request when current counter exceeds limit")
    void tryConsume_shouldRejectWhenLimitExceeded() {
        when(redisTemplate.execute(any(DefaultRedisScript.class), anyList(), eq("10"), eq("60")))
                .thenReturn(List.of(11L, 30L));

        RateLimitResult result = rateLimiterService.tryConsume("ip:127.0.0.1", 10, 60);

        assertThat(result.allowed()).isFalse();
        assertThat(result.limit()).isEqualTo(10);
        assertThat(result.remaining()).isZero();
        assertThat(result.resetSeconds()).isEqualTo(30);
    }

    @Test
    @DisplayName("tryConsume: Should fail-open and permit request if Redis is unavailable")
    void tryConsume_shouldFailOpenWhenRedisFails() {
        when(redisTemplate.execute(any(DefaultRedisScript.class), anyList(), eq("10"), eq("60")))
                .thenThrow(new RedisConnectionFailureException("Connection refused"));

        RateLimitResult result = rateLimiterService.tryConsume("ip:127.0.0.1", 10, 60);

        assertThat(result.allowed()).isTrue();
        assertThat(result.limit()).isEqualTo(10);
        assertThat(result.remaining()).isEqualTo(10);
    }
}
