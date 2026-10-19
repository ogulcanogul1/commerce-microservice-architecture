package com.dgl.order.lock;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import org.springframework.data.redis.core.script.RedisScript;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class RedisDistributedLockServiceTest {

    @Mock
    private StringRedisTemplate redisTemplate;

    @Mock
    private ValueOperations<String, String> valueOperations;

    @InjectMocks
    private RedisDistributedLockService lockService;

    private static final String LOCK_KEY = "test:lock:retention";
    private static final String LOCK_OWNER = "test-node-1";
    private static final Duration LEASE_TIME = Duration.ofMinutes(5);

    @BeforeEach
    void setUp() {
        lenient().when(redisTemplate.opsForValue()).thenReturn(valueOperations);
    }

    @Test
    @DisplayName("Should successfully acquire lock via Redis setIfAbsent (NX PX)")
    void shouldAcquireLockSuccessfully() {
        when(valueOperations.setIfAbsent(eq(LOCK_KEY), eq(LOCK_OWNER), eq(LEASE_TIME)))
                .thenReturn(Boolean.TRUE);

        boolean acquired = lockService.tryAcquire(LOCK_KEY, LOCK_OWNER, LEASE_TIME);

        assertThat(acquired).isTrue();
        verify(valueOperations).setIfAbsent(eq(LOCK_KEY), eq(LOCK_OWNER), eq(LEASE_TIME));
    }

    @Test
    @DisplayName("Should return false when lock is already held by another cluster instance")
    void shouldFailToAcquireWhenAlreadyHeld() {
        when(valueOperations.setIfAbsent(eq(LOCK_KEY), eq(LOCK_OWNER), eq(LEASE_TIME)))
                .thenReturn(Boolean.FALSE);

        boolean acquired = lockService.tryAcquire(LOCK_KEY, LOCK_OWNER, LEASE_TIME);

        assertThat(acquired).isFalse();
    }

    @Test
    @DisplayName("Should release lock via atomic Lua script when caller owns the lock")
    void shouldReleaseLockSuccessfully() {
        when(redisTemplate.execute(any(RedisScript.class), eq(List.of(LOCK_KEY)), eq(LOCK_OWNER)))
                .thenReturn(1L);

        boolean released = lockService.release(LOCK_KEY, LOCK_OWNER);

        assertThat(released).isTrue();
    }

    @Test
    @DisplayName("Should return false on release when caller is not the lock owner or lock expired")
    void shouldFailReleaseWhenNotOwner() {
        when(redisTemplate.execute(any(RedisScript.class), eq(List.of(LOCK_KEY)), eq(LOCK_OWNER)))
                .thenReturn(0L);

        boolean released = lockService.release(LOCK_KEY, LOCK_OWNER);

        assertThat(released).isFalse();
    }

    @Test
    @DisplayName("Should execute task under lock and release it when acquired")
    void shouldExecuteTaskUnderLock() {
        when(valueOperations.setIfAbsent(eq(LOCK_KEY), anyString(), eq(LEASE_TIME)))
                .thenReturn(Boolean.TRUE);
        when(redisTemplate.execute(any(RedisScript.class), eq(List.of(LOCK_KEY)), anyString()))
                .thenReturn(1L);

        AtomicBoolean taskExecuted = new AtomicBoolean(false);
        boolean result = lockService.executeWithLock(LOCK_KEY, LEASE_TIME, () -> taskExecuted.set(true));

        assertThat(result).isTrue();
        assertThat(taskExecuted.get()).isTrue();
        verify(valueOperations).setIfAbsent(eq(LOCK_KEY), anyString(), eq(LEASE_TIME));
        verify(redisTemplate).execute(any(RedisScript.class), eq(List.of(LOCK_KEY)), anyString());
    }

    @Test
    @DisplayName("Should skip task execution when lock cannot be acquired")
    void shouldSkipTaskWhenLockUnavailable() {
        when(valueOperations.setIfAbsent(eq(LOCK_KEY), anyString(), eq(LEASE_TIME)))
                .thenReturn(Boolean.FALSE);

        AtomicBoolean taskExecuted = new AtomicBoolean(false);
        boolean result = lockService.executeWithLock(LOCK_KEY, LEASE_TIME, () -> taskExecuted.set(true));

        assertThat(result).isFalse();
        assertThat(taskExecuted.get()).isFalse();
        verify(redisTemplate, never()).execute(any(RedisScript.class), anyList(), any());
    }
}
