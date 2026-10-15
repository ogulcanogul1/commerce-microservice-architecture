package com.dgl.e2e.scenarios;

import com.dgl.e2e.base.BaseE2ETest;
import io.restassured.response.Response;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

@DisplayName("E2E Scenario 4: API Gateway Rate Limiting & Traffic Shaping")
class RateLimitingE2ETest extends BaseE2ETest {

    @Test
    @DisplayName("Should process legitimate requests and shape traffic under burst conditions")
    void shouldHandleHighFrequencyTrafficThroughGateway() {
        int burstCount = 60;
        List<Integer> statusCodes = new ArrayList<>(burstCount);

        for (int i = 0; i < burstCount; i++) {
            Response resp = gatewayClient.getHealth();
            statusCodes.add(resp.statusCode());
        }

        long successCount = statusCodes.stream().filter(code -> code == 200).count();
        long rateLimitedCount = statusCodes.stream().filter(code -> code == 429).count();

        log.info("Rate Limiting Test: Burst={}, 200 OK={}, 429 TooManyRequests={}", burstCount, successCount, rateLimitedCount);

        // All responses must be either 200 (healthy) or 429 (rate-limited) - no 500 crashes
        assertThat(statusCodes).allMatch(code -> code == 200 || code == 429);
        assertThat(successCount).isGreaterThan(0);
    }
}
