package com.dgl.gateway.ratelimit;

import org.springframework.stereotype.Component;

import java.time.Clock;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Redis erişilemez olduğunda (fail-mode: LOCAL) süreç içi (in-memory) çalışan kayan pencere sınırlayıcısı.
 * Her API Gateway instance'ı kendi yerel sayacını bellekte tutarak AI servislerinin aşırı yüklenmesini
 * ve yüksek maliyet/token tüketimini önler.
 */
@Component
public class LocalSlidingWindowLimiter {

    private final Clock clock;
    private final ConcurrentHashMap<String, Deque<Long>> requestTimestamps = new ConcurrentHashMap<>();
    private final AtomicLong callCounter = new AtomicLong();

    public LocalSlidingWindowLimiter() {
        this(Clock.systemUTC());
    }

    public LocalSlidingWindowLimiter(Clock clock) {
        this.clock = clock;
    }

    /**
     * Verilen anahtar için yerel kayan pencere hız sınırını kontrol eder ve tüketir.
     *
     * @param key           Sınırlama kova anahtarı (ör. "ai-chat:user:123")
     * @param limit         Pencere içindeki maksimum istek sayısı
     * @param windowSeconds Pencere süresi (saniye)
     * @return Hız sınırı sonucu (izin verildi mi, kalan hak, sıfırlanma süresi)
     */
    public RateLimitResult tryConsume(String key, long limit, long windowSeconds) {
        long nowMs = clock.millis();
        long windowMs = windowSeconds * 1000L;
        long thresholdMs = nowMs - windowMs;

        // Bellek sızıntısını önlemek için her 1000 çağrıda bir eski anahtarları temizle
        if (callCounter.incrementAndGet() % 1000 == 0) {
            cleanup(thresholdMs);
        }

        Deque<Long> deque = requestTimestamps.computeIfAbsent(key, k -> new ArrayDeque<>());
        synchronized (deque) {
            // Pencere süresinden daha eski istek damgalarını baştan temizle
            while (!deque.isEmpty() && deque.peekFirst() <= thresholdMs) {
                deque.pollFirst();
            }

            int currentCount = deque.size();
            if (currentCount >= limit) {
                Long oldest = deque.peekFirst();
                long resetSeconds = oldest != null
                        ? Math.max(1, (oldest + windowMs - nowMs + 999) / 1000)
                        : windowSeconds;
                return new RateLimitResult(false, limit, 0, resetSeconds);
            }

            // Yeni isteğin zaman damgasını ekle
            deque.addLast(nowMs);
            long remaining = Math.max(0, limit - (currentCount + 1));
            long resetSeconds = windowSeconds;
            return new RateLimitResult(true, limit, remaining, resetSeconds);
        }
    }

    /**
     * Süresi dolmuş ve boşalmış olan kuyrukları haritadan (map) temizler.
     */
    private void cleanup(long thresholdMs) {
        requestTimestamps.entrySet().removeIf(entry -> {
            Deque<Long> deque = entry.getValue();
            synchronized (deque) {
                while (!deque.isEmpty() && deque.peekFirst() <= thresholdMs) {
                    deque.pollFirst();
                }
                return deque.isEmpty();
            }
        });
    }
}
