package com.dgl.e2e.scenarios;

import com.dgl.e2e.base.BaseE2ETest;
import io.restassured.RestAssured;
import io.restassured.response.Response;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

@DisplayName("E2E Scenario 6: Circuit Breaker & Graceful Fallback Degradation")
class CircuitBreakerFallbackE2ETest extends BaseE2ETest {

    @Test
    @DisplayName("Should return RFC 7807 503 Service Unavailable when circuit breaker opens or fallback is invoked")
    void shouldReturnProblemDetailOnFallback() {
        String[] fallbackServices = {"product", "order", "payment", "inventory", "shipping", "customer", "notification"};

        for (String service : fallbackServices) {
            Response response = RestAssured.given()
                    .baseUri(gatewayUrl)
                    .when()
                    .get("/fallback/" + service)
                    .then()
                    .statusCode(503)
                    .extract()
                    .response();

            String title = response.jsonPath().getString("title");
            String detail = response.jsonPath().getString("detail");
            int status = response.jsonPath().getInt("status");

            assertThat(status).isEqualTo(503);
            assertThat(title).isEqualTo("Service Temporarily Unavailable");
            assertThat(detail).containsIgnoringCase(service);

            log.info("Circuit Breaker Fallback verified for {} service: status={}, detail={}",
                    service, status, detail);
        }
    }
}
