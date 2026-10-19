package com.dgl.order.lock;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.util.Collections;
import java.util.UUID;

/**
 * Production-grade Redis distributed lock implementation using atomic
 * SET key value NX PX and Lua script for safe, owner-verified release.
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class RedisDistributedLockService implements DistributedLockService {

    private final StringRedisTemplate redisTemplate;

    // Atomic Lua script to ensure safe release: only delete key if value matches owner
    private static final String RELEASE_LOCK_LUA_SCRIPT =
            "if redis.call('get', KEYS[1]) == ARGV[1] then " +
            "    return redis.call('del', KEYS[1]) " +
            "else " +
            "    return 0 " +
            "end";

    private final DefaultRedisScript<Long> releaseScript = new DefaultRedisScript<>(RELEASE_LOCK_LUA_SCRIPT, Long.class);

    @Override
    public boolean tryAcquire(String lockKey, String lockOwner, Duration leaseTime) {
        try {
            Boolean acquired = redisTemplate.opsForValue().setIfAbsent(lockKey, lockOwner, leaseTime);
            return Boolean.TRUE.equals(acquired);
        } catch (Exception ex) {
            log.error("Failed to acquire distributed lock for key [{}]: {}", lockKey, ex.getMessage());
            return false;
        }
    }

    @Override
    public boolean release(String lockKey, String lockOwner) {
        try {
            Long result = redisTemplate.execute(releaseScript, Collections.singletonList(lockKey), lockOwner);
            return result != null && result > 0;
        } catch (Exception ex) {
            log.error("Failed to release distributed lock for key [{}]: {}", lockKey, ex.getMessage());
            return false;
        }
    }

    @Override
    public boolean executeWithLock(String lockKey, Duration leaseTime, Runnable task) {
        String lockOwner = UUID.randomUUID() + "@" + Thread.currentThread().getName();

        if (!tryAcquire(lockKey, lockOwner, leaseTime)) {
            log.info("Distributed task skipped: lock [{}] is held by another cluster instance.", lockKey);
            return false;
        }

        log.info("Successfully acquired distributed lock [{}] for owner [{}] (lease: {}). Executing task...",
                lockKey, lockOwner, leaseTime);
        try {
            task.run();
            return true;
        } finally {
            boolean released = release(lockKey, lockOwner);
            if (released) {
                log.info("Successfully released distributed lock [{}] for owner [{}]", lockKey, lockOwner);
            } else {
                log.warn("Could not release distributed lock [{}] for owner [{}] (lease may have expired).", lockKey, lockOwner);
            }
        }
    }
}
