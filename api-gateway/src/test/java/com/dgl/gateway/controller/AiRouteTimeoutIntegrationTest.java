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
@org.springframework.test.context.ActiveProfiles("test")
class AiRouteTimeoutIntegrationTest {

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

        // /agent/chat: 1200 ms gecikme ile 200 OK döner
        mockAiBackend.createContext("/agent/chat", exchange -> {
            System.out.println("MOCK BACKEND RECEIVED: " + exchange.getRequestURI());
            try {
                Thread.sleep(1200);
            } catch (InterruptedException ignored) {}
            byte[] response = "{\"reply\":\"success\"}".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, response.length);
            try (OutputStream os = exchange.getResponseBody()) {
                os.write(response);
            }
        });

        // /rag/search: 1200 ms gecikme ile döner
        mockAiBackend.createContext("/rag/search", exchange -> {
            System.out.println("MOCK BACKEND RECEIVED: " + exchange.getRequestURI());
            try {
                Thread.sleep(1200);
            } catch (InterruptedException ignored) {}
            byte[] response = "{\"results\":[]}".getBytes(StandardCharsets.UTF_8);
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
        // Test için süreleri kontrollü ayarlıyoruz:
        // aiChatCircuitBreaker için 5s (1.2s gecikme başarıyla geçer -> 200 OK)
        registry.add("resilience4j.timelimiter.instances.aiChatCircuitBreaker.timeoutDuration", () -> "5s");
        // aiRagSearchCircuitBreaker için 500ms (1.2s gecikme zaman aşımına uğrar -> 503 fallback)
        registry.add("resilience4j.timelimiter.instances.aiRagSearchCircuitBreaker.timeoutDuration", () -> "500ms");
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
    @DisplayName("7a. Characterization Test: ai-chat route should NOT time out when duration is within timelimiter")
    void aiChatRoute_ShouldNotTimeoutWhenWithinLimit() throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://localhost:" + gatewayPort + "/agent/chat"))
                .header("Authorization", "Bearer " + generateTestJwt())
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString("{\"message\":\"hello\"}"))
                .build();

        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        System.out.println("DEBUG BODY: " + response.body() + " STATUS: " + response.statusCode());

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.body()).contains("reply");
    }

    @Test
    @DisplayName("7a. Characterization Test: ai-rag-search route should time out and trigger fallback when duration exceeds timelimiter")
    void aiRagSearchRoute_ShouldTimeoutAndTriggerFallbackWhenExceedingLimit() throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://localhost:" + gatewayPort + "/rag/search"))
                .header("Authorization", "Bearer " + generateTestJwt())
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString("{\"query\":\"policy\"}"))
                .build();

        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        System.out.println("RAG SEARCH STATUS: " + response.statusCode() + " BODY: " + response.body());

        assertThat(response.statusCode()).isEqualTo(503);
        assertThat(response.body()).contains("ai-rag-unavailable");
    }
}
