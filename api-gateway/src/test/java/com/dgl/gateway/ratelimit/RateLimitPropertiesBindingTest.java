package com.dgl.gateway.ratelimit;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.ConfigurationPropertySources;
import org.springframework.mock.env.MockEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class RateLimitPropertiesBindingTest {

    @Test
    @DisplayName("RateLimitProperties: Should successfully bind policies from environment properties")
    void shouldBindPoliciesFromConfigurationProperties() {
        MockEnvironment environment = new MockEnvironment();
        environment.setProperty("rate-limiter.enabled", "true");
        environment.setProperty("rate-limiter.trust-forwarded-for", "false");

        environment.setProperty("rate-limiter.policies[0].name", "ai-actions");
        environment.setProperty("rate-limiter.policies[0].path-patterns[0]", "/agent/actions/**");
        environment.setProperty("rate-limiter.policies[0].path-patterns[1]", "/api/v1/chat/actions/**");
        environment.setProperty("rate-limiter.policies[0].limit", "20");
        environment.setProperty("rate-limiter.policies[0].window-seconds", "60");
        environment.setProperty("rate-limiter.policies[0].algorithm", "SLIDING_WINDOW");
        environment.setProperty("rate-limiter.policies[0].fail-mode", "LOCAL");

        environment.setProperty("rate-limiter.policies[1].name", "ai-chat");
        environment.setProperty("rate-limiter.policies[1].path-patterns[0]", "/agent");
        environment.setProperty("rate-limiter.policies[1].limit", "10");
        environment.setProperty("rate-limiter.policies[1].window-seconds", "60");

        Binder binder = new Binder(ConfigurationPropertySources.get(environment));
        RateLimitProperties properties = binder.bind("rate-limiter", RateLimitProperties.class).get();

        assertThat(properties).isNotNull();
        assertThat(properties.isEnabled()).isTrue();
        assertThat(properties.isTrustForwardedFor()).isFalse();
        assertThat(properties.getPolicies()).hasSize(2);

        RateLimitPolicy p0 = properties.getPolicies().get(0);
        assertThat(p0.name()).isEqualTo("ai-actions");
        assertThat(p0.pathPatterns()).containsExactly("/agent/actions/**", "/api/v1/chat/actions/**");
        assertThat(p0.limit()).isEqualTo(20);
        assertThat(p0.windowSeconds()).isEqualTo(60);
        assertThat(p0.algorithm()).isEqualTo(RateLimitPolicy.Algorithm.SLIDING_WINDOW);
        assertThat(p0.failMode()).isEqualTo(RateLimitPolicy.FailMode.LOCAL);

        RateLimitPolicy p1 = properties.getPolicies().get(1);
        assertThat(p1.name()).isEqualTo("ai-chat");
        assertThat(p1.limit()).isEqualTo(10);
        assertThat(p1.windowSeconds()).isEqualTo(60);
        assertThat(p1.algorithm()).isEqualTo(RateLimitPolicy.Algorithm.SLIDING_WINDOW);
        assertThat(p1.failMode()).isEqualTo(RateLimitPolicy.FailMode.LOCAL);
    }
}
