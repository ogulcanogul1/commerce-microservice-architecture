package com.dgl.gateway.ratelimit;

import org.springframework.boot.context.properties.bind.DefaultValue;

import java.util.List;

/**
 * Rota bazlı hız sınırlama politikası tanımı (Rate Limit Policy).
 * Her rota kümesi için kova limiti, pencere süresi, algoritma ve Redis arızasında
 * uygulanacak fail modu (LOCAL / OPEN) bu kayıt (record) ile yapılandırılır.
 */
public record RateLimitPolicy(
        String name,
        List<String> pathPatterns,
        long limit,
        long windowSeconds,
        @DefaultValue("SLIDING_WINDOW") Algorithm algorithm,
        @DefaultValue("LOCAL") FailMode failMode
) {
    public enum Algorithm {
        FIXED_WINDOW,
        SLIDING_WINDOW
    }

    public enum FailMode {
        OPEN,
        LOCAL
    }

    /**
     * Testler ve pratik nesne oluşturma için yardımcı kurucu metot.
     * Varsayılan olarak SLIDING_WINDOW ve LOCAL fail modunu kullanır.
     */
    public RateLimitPolicy(String name, List<String> pathPatterns, long limit, long windowSeconds) {
        this(name, pathPatterns, limit, windowSeconds, Algorithm.SLIDING_WINDOW, FailMode.LOCAL);
    }
}
