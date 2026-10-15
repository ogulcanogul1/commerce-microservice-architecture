package com.dgl.e2e.base;

import com.dgl.e2e.client.GatewayClient;
import io.restassured.response.Response;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.TestInstance;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Duration;

import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
public abstract class BaseE2ETest {

    protected final Logger log = LoggerFactory.getLogger(getClass());

    protected String gatewayUrl;
    protected GatewayClient gatewayClient;

    @BeforeAll
    void initSuite() {
        this.gatewayUrl = System.getenv().getOrDefault("TARGET_GATEWAY_URL", "http://localhost:8080");
        this.gatewayClient = new GatewayClient(gatewayUrl);
        log.info("Initialized E2E Suite targeting Gateway URL: {}", gatewayUrl);
    }

    @BeforeEach
    void verifyGatewayAvailability() {
        boolean isUp = checkGatewayHealth();
        assumeTrue(isUp, "API Gateway is unreachable at " + gatewayUrl + ". Skipping E2E test. Start services or docker-compose to run.");
    }

    protected boolean checkGatewayHealth() {
        try {
            Response response = gatewayClient.getHealth();
            return response.statusCode() == 200;
        } catch (Exception e) {
            log.warn("Gateway health check failed at {}: {}", gatewayUrl, e.getMessage());
            return false;
        }
    }

    protected Duration defaultTimeout() {
        return Duration.ofSeconds(20);
    }

    protected Duration pollInterval() {
        return Duration.ofMillis(1000);
    }
}
