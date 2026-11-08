package com.dgl.gateway.config;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import io.github.resilience4j.timelimiter.TimeLimiterConfig;
import io.github.resilience4j.timelimiter.TimeLimiterRegistry;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JCircuitBreakerFactory;
import org.springframework.cloud.circuitbreaker.resilience4j.Resilience4JConfigBuilder;
import org.springframework.cloud.client.circuitbreaker.Customizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Gateway için Resilience4j Circuit Breaker ve TimeLimiter özelleştirmeleri (Adım 7c).
 * Rota bazlı zaman aşımı (TimeLimiter) ve devre kesici eşiklerinin
 * Spring Cloud Gateway Server WebMVC üzerinde kesin olarak uygulanmasını garanti eder.
 */
@Configuration
public class ResilienceConfig {

    @Bean
    public Customizer<Resilience4JCircuitBreakerFactory> defaultCustomizer(
            CircuitBreakerRegistry circuitBreakerRegistry,
            TimeLimiterRegistry timeLimiterRegistry) {
        return factory -> {
            factory.configureDefault(id -> {
                CircuitBreakerConfig cbConfig = circuitBreakerRegistry.getConfiguration(id)
                        .or(() -> circuitBreakerRegistry.find(id).map(io.github.resilience4j.circuitbreaker.CircuitBreaker::getCircuitBreakerConfig))
                        .orElseGet(circuitBreakerRegistry::getDefaultConfig);

                TimeLimiterConfig tlConfig = timeLimiterRegistry.getConfiguration(id)
                        .or(() -> timeLimiterRegistry.find(id).map(io.github.resilience4j.timelimiter.TimeLimiter::getTimeLimiterConfig))
                        .orElseGet(timeLimiterRegistry::getDefaultConfig);

                return new Resilience4JConfigBuilder(id)
                        .circuitBreakerConfig(cbConfig)
                        .timeLimiterConfig(tlConfig)
                        .build();
            });
        };
    }
}
