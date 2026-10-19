package com.dgl.order.lock;

import java.time.Duration;

/**
 * Distributed Lock interface for synchronizing tasks across multiple
 * horizontally-scaled instances in a distributed microservice cluster.
 */
public interface DistributedLockService {

    /**
     * Attempts to acquire a distributed lock.
     *
     * @param lockKey   The identifier of the resource/job to lock.
     * @param lockOwner The unique identity of the acquiring node/thread.
     * @param leaseTime The duration after which the lock is automatically released to prevent deadlocks.
     * @return true if acquired successfully, false otherwise.
     */
    boolean tryAcquire(String lockKey, String lockOwner, Duration leaseTime);

    /**
     * Safely releases a distributed lock using an atomic check to guarantee
     * only the current owner can release it.
     *
     * @param lockKey   The identifier of the lock.
     * @param lockOwner The unique identity of the releasing node/thread.
     * @return true if released, false if not owned or already expired.
     */
    boolean release(String lockKey, String lockOwner);

    /**
     * Executes the given task exclusively if the lock can be acquired.
     * Skips execution if another node is currently holding the lock.
     *
     * @param lockKey   The identifier of the lock.
     * @param leaseTime Maximum time the lock can be held before auto-expiring.
     * @param task      The task to execute.
     * @return true if the task was executed, false if skipped because lock was unavailable.
     */
    boolean executeWithLock(String lockKey, Duration leaseTime, Runnable task);
}
