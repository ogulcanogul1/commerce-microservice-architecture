package com.dgl.gateway.ratelimit;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Service;

import java.time.Clock;
import java.util.Collections;
import java.util.List;

/**
 * Dağıtık hız sınırlayıcı servisi (Distributed Rate Limiter Service).
 * Redis tabanlı çalışır ve atomik Lua betikleri yürütür.
 * İki algoritmayı destekler:
 * 1. Sabit Pencere (Fixed Window) - Mevcut varsayılan rotalar için (fail-open)
 * 2. Kayan Pencere (Sliding Window Counter) - AI rotaları için (Redis çökünce fail-mode: LOCAL ile süreç içi sınırlayıcıya geçer)
 */
@Slf4j
@Service
public class RateLimiterService {

    private final StringRedisTemplate redisTemplate;
    private final LocalSlidingWindowLimiter localLimiter;
    private final Clock clock;

    /**
     * Sabit Pencere (Fixed Window) Hız Sınırı Lua Betiği:
     * Sayaç anahtarını 1 artırır, ilk oluşturulmada pencere süresi kadar TTL atar.
     */
    private static final String FIXED_LUA_SCRIPT =
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

    /**
     * Kayan Pencere (Sliding Window Counter) Hız Sınırı Lua Betiği:
     * İki ardışık pencereyi (şimdiki ve önceki) kullanarak pencere sınırlarındaki
     * ani yük patlamalarını (burst) engeller ve ağırlıklı ortalama ile kalan kotayı hesaplar.
     *
     * KEYS[1] = Şimdiki zaman penceresi anahtarı (rate_limit:{key}:{idx})
     * KEYS[2] = Önceki zaman penceresi anahtarı (rate_limit:{key}:{idx-1})
     * ARGV[1] = İzin verilen maksimum istek limiti
     * ARGV[2] = Pencere süresi (milisaniye cinsinden, windowMs)
     * ARGV[3] = Şimdiki pencere içinde geçen süre (milisaniye cinsinden, elapsed)
     */
    private static final String SLIDING_LUA_SCRIPT =
            "-- 1. Gelen argümanları sayı formatına dönüştür\n" +
            "local limit = tonumber(ARGV[1])\n" +
            "local windowMs = tonumber(ARGV[2])\n" +
            "local elapsed = tonumber(ARGV[3])\n" +
            "\n" +
            "-- 2. Önceki ve şimdiki penceredeki mevcut istek sayılarını Redis'ten oku (yoksa 0)\n" +
            "local prev = tonumber(redis.call('GET', KEYS[2]) or '0')\n" +
            "local cur = tonumber(redis.call('GET', KEYS[1]) or '0')\n" +
            "\n" +
            "-- 3. Önceki pencerenin ağırlığını hesapla: Şimdiki pencerede geçen süre arttıkça önceki pencerenin etkisi azalır\n" +
            "local weight = (windowMs - elapsed) / windowMs\n" +
            "local estimated = cur + prev * weight\n" +
            "local resetSec = math.ceil((windowMs - elapsed) / 1000)\n" +
            "\n" +
            "-- 4. Tahmini istek sayısı limiti aşıyorsa isteği engelle (0 dön)\n" +
            "if estimated + 1 > limit then\n" +
            "    return { 0, resetSec, 0 }\n" +
            "end\n" +
            "\n" +
            "-- 5. Limit aşılmadıysa şimdiki pencere sayacını 1 artır\n" +
            "local v = redis.call('INCR', KEYS[1])\n" +
            "\n" +
            "-- 6. Şimdiki pencere yeni açıldıysa hafızada kalması için 2 pencere süresi kadar TTL (PEXPIRE) ata\n" +
            "if v == 1 then\n" +
            "    redis.call('PEXPIRE', KEYS[1], windowMs * 2)\n" +
            "end\n" +
            "\n" +
            "-- 7. Başarılı sonuç dön: { izin_verildi(1), sıfırlanma_süresi, kalan_kota }\n" +
            "return { 1, resetSec, math.max(0, math.floor(limit - (estimated + 1))) }";

    @SuppressWarnings("rawtypes")
    private final DefaultRedisScript<List> fixedRedisScript = new DefaultRedisScript<>(FIXED_LUA_SCRIPT, List.class);

    @SuppressWarnings("rawtypes")
    private final DefaultRedisScript<List> slidingRedisScript = new DefaultRedisScript<>(SLIDING_LUA_SCRIPT, List.class);

    @Autowired
    public RateLimiterService(StringRedisTemplate redisTemplate, LocalSlidingWindowLimiter localLimiter) {
        this(redisTemplate, localLimiter, Clock.systemUTC());
    }

    public RateLimiterService(StringRedisTemplate redisTemplate, LocalSlidingWindowLimiter localLimiter, Clock clock) {
        this.redisTemplate = redisTemplate;
        this.localLimiter = localLimiter;
        this.clock = clock != null ? clock : Clock.systemUTC();
    }

    /**
     * Sabit pencere algoritması ile hız sınırı tüketimi.
     * Mevcut genel rotalar için geriye uyumlu olarak kullanılır.
     */
    @SuppressWarnings("unchecked")
    public RateLimitResult tryConsume(String key, long limit, long windowSeconds) {
        String redisKey = "rate_limit:" + key;
        try {
            List<Long> result = redisTemplate.execute(
                    fixedRedisScript,
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

    /**
     * Kayan pencere (Sliding Window Counter) algoritması ile hız sınırı tüketimi.
     * AI gibi pahalı kaynakları koruyan rotalar için kullanılır.
     * Redis kesintisinde failMode'a göre LOCAL (bellek içi yedek limiter) veya OPEN moduna geçer.
     */
    public RateLimitResult tryConsumeSliding(
            String key,
            long limit,
            long windowSeconds,
            RateLimitPolicy.FailMode failMode) {

        long nowMs = clock.millis();
        long windowMs = windowSeconds * 1000L;
        long idx = nowMs / windowMs;
        long elapsed = nowMs % windowMs;

        String curKey = "rate_limit:" + key + ":" + idx;
        String prevKey = "rate_limit:" + key + ":" + (idx - 1);

        try {
            List<?> result = redisTemplate.execute(
                    slidingRedisScript,
                    List.of(curKey, prevKey),
                    String.valueOf(limit),
                    String.valueOf(windowMs),
                    String.valueOf(elapsed)
            );

            if (result != null && result.size() >= 3) {
                boolean allowed = ((Number) result.get(0)).longValue() == 1L;
                long resetSeconds = ((Number) result.get(1)).longValue();
                long remaining = ((Number) result.get(2)).longValue();
                return new RateLimitResult(allowed, limit, remaining, resetSeconds);
            }
        } catch (Exception ex) {
            if (failMode == RateLimitPolicy.FailMode.LOCAL) {
                // Güvenlik ve log temizliği kuralı: Anahtar bilgisi loglanmaz, yalnızca hata tipi loglanır
                log.warn("Redis rate limiter unavailable ({}). Degrading to local in-memory limiter.",
                        ex.getClass().getSimpleName());
                return localLimiter.tryConsume(key, limit, windowSeconds);
            }
            log.warn("Redis rate limiter unavailable ({}). Degrading to fail-open.",
                    ex.getClass().getSimpleName());
            return new RateLimitResult(true, limit, limit, 0);
        }

        return new RateLimitResult(true, limit, limit, 0);
    }
}
