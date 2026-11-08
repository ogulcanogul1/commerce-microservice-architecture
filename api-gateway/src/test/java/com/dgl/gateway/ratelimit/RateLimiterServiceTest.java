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
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class RateLimiterServiceTest {

    @Mock
    private StringRedisTemplate redisTemplate;

    @Mock
    private LocalSlidingWindowLimiter localLimiter;

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

    @Test
    @DisplayName("tryConsumeSliding: Should permit request when sliding window Lua returns allowed=1")
    void tryConsumeSliding_shouldAllowWhenWithinLimit() {
        when(redisTemplate.execute(any(DefaultRedisScript.class), anyList(), eq("10"), eq("60000"), any()))
                .thenReturn(List.of(1L, 45L, 7L));

        RateLimitResult result = rateLimiterService.tryConsumeSliding("ai-chat:user:1", 10, 60, RateLimitPolicy.FailMode.LOCAL);

        assertThat(result.allowed()).isTrue();
        assertThat(result.limit()).isEqualTo(10);
        assertThat(result.remaining()).isEqualTo(7);
        assertThat(result.resetSeconds()).isEqualTo(45);
    }

    @Test
    @DisplayName("tryConsumeSliding: Should reject request when sliding window Lua returns allowed=0")
    void tryConsumeSliding_shouldRejectWhenLimitExceeded() {
        when(redisTemplate.execute(any(DefaultRedisScript.class), anyList(), eq("10"), eq("60000"), any()))
                .thenReturn(List.of(0L, 30L, 0L));

        RateLimitResult result = rateLimiterService.tryConsumeSliding("ai-chat:user:1", 10, 60, RateLimitPolicy.FailMode.LOCAL);

        assertThat(result.allowed()).isFalse();
        assertThat(result.limit()).isEqualTo(10);
        assertThat(result.remaining()).isZero();
        assertThat(result.resetSeconds()).isEqualTo(30);
    }

    @Test
    @DisplayName("tryConsumeSliding: Should fallback to local in-memory limiter when Redis fails and fail-mode is LOCAL")
    void tryConsumeSliding_shouldFallbackToLocalWhenRedisFailsAndFailModeLocal() {
        when(redisTemplate.execute(any(DefaultRedisScript.class), anyList(), any(), any(), any()))
                .thenThrow(new RedisConnectionFailureException("Connection refused"));

        when(localLimiter.tryConsume("ai-chat:user:1", 10, 60))
                .thenReturn(new RateLimitResult(false, 10, 0, 45));

        RateLimitResult result = rateLimiterService.tryConsumeSliding("ai-chat:user:1", 10, 60, RateLimitPolicy.FailMode.LOCAL);

        assertThat(result.allowed()).isFalse();
        assertThat(result.limit()).isEqualTo(10);
        verify(localLimiter).tryConsume("ai-chat:user:1", 10, 60);
    }

    @Test
    @DisplayName("tryConsumeSliding: Should fail-open when Redis fails and fail-mode is OPEN")
    void tryConsumeSliding_shouldFailOpenWhenRedisFailsAndFailModeOpen() {
        when(redisTemplate.execute(any(DefaultRedisScript.class), anyList(), any(), any(), any()))
                .thenThrow(new RedisConnectionFailureException("Connection refused"));

        RateLimitResult result = rateLimiterService.tryConsumeSliding("search:user:1", 10, 60, RateLimitPolicy.FailMode.OPEN);

        assertThat(result.allowed()).isTrue();
        assertThat(result.limit()).isEqualTo(10);
        verify(localLimiter, never()).tryConsume(any(), anyLong(), anyLong());
    }
}
