package com.dgl.gateway.ratelimit;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;

class LocalSlidingWindowLimiterTest {

    private static class MutableClock extends Clock {
        private final AtomicReference<Instant> currentInstant;
        private final ZoneId zone = ZoneId.of("UTC");

        public MutableClock(Instant initial) {
            this.currentInstant = new AtomicReference<>(initial);
        }

        public void advanceSeconds(long seconds) {
            currentInstant.updateAndGet(i -> i.plusSeconds(seconds));
        }

        @Override
        public ZoneId getZone() {
            return zone;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            return this;
        }

        @Override
        public Instant instant() {
            return currentInstant.get();
        }
    }

    @Test
    @DisplayName("tryConsume: Should permit requests within the limit and decrement remaining")
    void tryConsume_shouldPermitWithinLimit() {
        MutableClock clock = new MutableClock(Instant.parse("2026-10-01T12:00:00Z"));
        LocalSlidingWindowLimiter limiter = new LocalSlidingWindowLimiter(clock);

        RateLimitResult res1 = limiter.tryConsume("user:1", 3, 60);
        assertThat(res1.allowed()).isTrue();
        assertThat(res1.remaining()).isEqualTo(2);

        RateLimitResult res2 = limiter.tryConsume("user:1", 3, 60);
        assertThat(res2.allowed()).isTrue();
        assertThat(res2.remaining()).isEqualTo(1);

        RateLimitResult res3 = limiter.tryConsume("user:1", 3, 60);
        assertThat(res3.allowed()).isTrue();
        assertThat(res3.remaining()).isZero();
    }

    @Test
    @DisplayName("tryConsume: Should reject request when limit is exceeded")
    void tryConsume_shouldRejectWhenLimitExceeded() {
        MutableClock clock = new MutableClock(Instant.parse("2026-10-01T12:00:00Z"));
        LocalSlidingWindowLimiter limiter = new LocalSlidingWindowLimiter(clock);

        limiter.tryConsume("user:2", 2, 60);
        limiter.tryConsume("user:2", 2, 60);

        RateLimitResult blocked = limiter.tryConsume("user:2", 2, 60);
        assertThat(blocked.allowed()).isFalse();
        assertThat(blocked.remaining()).isZero();
        assertThat(blocked.resetSeconds()).isGreaterThan(0);
    }

    @Test
    @DisplayName("tryConsume: Should allow requests again after window passes")
    void tryConsume_shouldAllowAgainAfterWindowExpires() {
        MutableClock clock = new MutableClock(Instant.parse("2026-10-01T12:00:00Z"));
        LocalSlidingWindowLimiter limiter = new LocalSlidingWindowLimiter(clock);

        limiter.tryConsume("user:3", 1, 60);
        RateLimitResult blocked = limiter.tryConsume("user:3", 1, 60);
        assertThat(blocked.allowed()).isFalse();

        // 61 saniye ilerlet (pencere süresi doldu)
        clock.advanceSeconds(61);

        RateLimitResult permitted = limiter.tryConsume("user:3", 1, 60);
        assertThat(permitted.allowed()).isTrue();
        assertThat(permitted.remaining()).isZero();
    }

    @Test
    @DisplayName("tryConsume: Different keys should have isolated rate limit buckets")
    void tryConsume_differentKeysShouldBeIsolated() {
        MutableClock clock = new MutableClock(Instant.parse("2026-10-01T12:00:00Z"));
        LocalSlidingWindowLimiter limiter = new LocalSlidingWindowLimiter(clock);

        limiter.tryConsume("key-A", 1, 60);
        RateLimitResult blockedA = limiter.tryConsume("key-A", 1, 60);
        assertThat(blockedA.allowed()).isFalse();

        RateLimitResult allowedB = limiter.tryConsume("key-B", 1, 60);
        assertThat(allowedB.allowed()).isTrue();
    }
}
