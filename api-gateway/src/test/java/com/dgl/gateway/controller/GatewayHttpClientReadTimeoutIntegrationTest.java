package com.dgl.gateway.controller;

import com.sun.net.httpserver.HttpServer;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import javax.crypto.SecretKey;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Date;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class GatewayHttpClientReadTimeoutIntegrationTest {

    private static HttpServer mockAiBackend;
    private static int mockPort;

    private static final String JWT_SECRET = "dgl-super-secret-jwt-signing-key-commerce-platform-2026-secure";

    @LocalServerPort
    private int gatewayPort;

    private final HttpClient httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    @BeforeAll
    static void startMockBackend() throws Exception {
        mockAiBackend = HttpServer.create(new InetSocketAddress(0), 0);
        mockPort = mockAiBackend.getAddress().getPort();

        mockAiBackend.createContext("/agent/chat", exchange -> {
            try {
                Thread.sleep(3000);
            } catch (InterruptedException ignored) {}
            byte[] response = "{\"reply\":\"success\"}".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, response.length);
            try (OutputStream os = exchange.getResponseBody()) {
                os.write(response);
            }
        });

        mockAiBackend.start();
    }

    @AfterAll
    static void stopMockBackend() {
        if (mockAiBackend != null) {
            mockAiBackend.stop(0);
        }
    }

    @DynamicPropertySource
    static void configureProperties(DynamicPropertyRegistry registry) {
        registry.add("SERVICES_AI_ASSISTANT_URL", () -> "http://localhost:" + mockPort);
        registry.add("resilience4j.timelimiter.instances.aiChatCircuitBreaker.timeoutDuration", () -> "10s");
        registry.add("spring.http.clients.read-timeout", () -> "1s");
    }

    private String generateTestJwt() {
        SecretKey key = Keys.hmacShaKeyFor(JWT_SECRET.getBytes(StandardCharsets.UTF_8));
        return Jwts.builder()
                .subject(UUID.randomUUID().toString())
                .claim("email", "test@commerce.com")
                .claim("role", "ROLE_CUSTOMER")
                .issuedAt(new Date())
                .expiration(new Date(System.currentTimeMillis() + 60000))
                .signWith(key)
                .compact();
    }

    @Test
    @DisplayName("spring.http.clients.read-timeout should trigger read timeout and fallback before timelimiter")
    void httpClientReadTimeout_ShouldTriggerFallbackBeforeTimeLimiter() throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://localhost:" + gatewayPort + "/agent/chat"))
                .header("Authorization", "Bearer " + generateTestJwt())
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString("{\"message\":\"hello\"}"))
                .build();

        long start = System.currentTimeMillis();
        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        long elapsed = System.currentTimeMillis() - start;

        assertThat(response.statusCode()).isEqualTo(503);
        assertThat(elapsed).isLessThan(2800L);
    }
}
