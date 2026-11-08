package com.dgl.gateway.filter;

import com.dgl.gateway.ratelimit.RateLimitPolicy;
import com.dgl.gateway.ratelimit.RateLimitProperties;
import com.dgl.gateway.ratelimit.RateLimitResult;
import com.dgl.gateway.ratelimit.RateLimiterService;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletResponse;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.test.util.ReflectionTestUtils;

import java.io.IOException;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class RateLimitingFilterTest {

    @Mock
    private RateLimiterService rateLimiterService;

    @Mock
    private FilterChain filterChain;

    @InjectMocks
    private RateLimitingFilter rateLimitingFilter;

    @BeforeEach
    void setUp() {
        ReflectionTestUtils.setField(rateLimitingFilter, "enabled", true);
        ReflectionTestUtils.setField(rateLimitingFilter, "anonymousLimit", 10L);
        ReflectionTestUtils.setField(rateLimitingFilter, "anonymousWindowSeconds", 60L);
        ReflectionTestUtils.setField(rateLimitingFilter, "authenticatedLimit", 60L);
        ReflectionTestUtils.setField(rateLimitingFilter, "authenticatedWindowSeconds", 60L);

        RateLimitProperties properties = new RateLimitProperties();
        properties.setEnabled(true);
        properties.setTrustForwardedFor(false);
        properties.setPolicies(List.of(
                new RateLimitPolicy("ai-actions", List.of("/agent/actions/**", "/api/v1/chat/actions/**"), 20, 60,
                        RateLimitPolicy.Algorithm.SLIDING_WINDOW, RateLimitPolicy.FailMode.LOCAL),
                new RateLimitPolicy("ai-chat", List.of("/agent", "/agent/chat", "/api/v1/chat", "/api/v1/chat/chat"), 10, 60,
                        RateLimitPolicy.Algorithm.SLIDING_WINDOW, RateLimitPolicy.FailMode.LOCAL),
                new RateLimitPolicy("ai-rag-answer", List.of("/rag/answer"), 10, 60,
                        RateLimitPolicy.Algorithm.SLIDING_WINDOW, RateLimitPolicy.FailMode.LOCAL),
                new RateLimitPolicy("ai-rag-search", List.of("/rag/search"), 30, 60,
                        RateLimitPolicy.Algorithm.SLIDING_WINDOW, RateLimitPolicy.FailMode.LOCAL)
        ));
        ReflectionTestUtils.setField(rateLimitingFilter, "rateLimitProperties", properties);
    }

    @Test
    @DisplayName("doFilterInternal: Should allow request and attach rate limit headers when quota is available")
    void doFilterInternal_shouldAllowRequestWhenWithinLimit() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/v1/products");
        request.setRemoteAddr("192.168.1.100");
        MockHttpServletResponse response = new MockHttpServletResponse();

        when(rateLimiterService.tryConsume(eq("ip:192.168.1.100"), eq(10L), eq(60L)))
                .thenReturn(new RateLimitResult(true, 10, 8, 45));

        rateLimitingFilter.doFilterInternal(request, response, filterChain);

        assertThat(response.getStatus()).isEqualTo(HttpServletResponse.SC_OK);
        assertThat(response.getHeader("X-RateLimit-Limit")).isEqualTo("10");
        assertThat(response.getHeader("X-RateLimit-Remaining")).isEqualTo("8");
        assertThat(response.getHeader("X-RateLimit-Reset")).isEqualTo("45");
        verify(filterChain).doFilter(request, response);
    }

    @Test
    @DisplayName("doFilterInternal: Should block request with HTTP 429 when quota is exceeded")
    void doFilterInternal_shouldBlockWith429WhenLimitExceeded() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/v1/products");
        request.setRemoteAddr("192.168.1.100");
        MockHttpServletResponse response = new MockHttpServletResponse();

        when(rateLimiterService.tryConsume(eq("ip:192.168.1.100"), eq(10L), eq(60L)))
                .thenReturn(new RateLimitResult(false, 10, 0, 30));

        rateLimitingFilter.doFilterInternal(request, response, filterChain);

        assertThat(response.getStatus()).isEqualTo(429);
        assertThat(response.getHeader("Retry-After")).isEqualTo("30");
        assertThat(response.getContentAsString()).contains("Rate limit exceeded");
        assertThat(response.getContentAsString()).contains("\"policy\":\"default\"");
        verify(filterChain, never()).doFilter(any(), any());
    }

    @Test
    @DisplayName("doFilterInternal: Should apply higher authenticated quota when X-User-Id is present on general route")
    void doFilterInternal_shouldUseUserQuotaWhenAuthenticated() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/api/v1/orders");
        request.addHeader(JwtAuthenticationFilter.USER_ID_HEADER, "user-uuid-123");
        MockHttpServletResponse response = new MockHttpServletResponse();

        when(rateLimiterService.tryConsume(eq("user:user-uuid-123"), eq(60L), eq(60L)))
                .thenReturn(new RateLimitResult(true, 60, 59, 58));

        rateLimitingFilter.doFilterInternal(request, response, filterChain);

        assertThat(response.getStatus()).isEqualTo(HttpServletResponse.SC_OK);
        assertThat(response.getHeader("X-RateLimit-Limit")).isEqualTo("60");
        verify(filterChain).doFilter(request, response);
    }

    @Test
    @DisplayName("doFilterInternal: Should bypass rate limiting for exempt actuator endpoints")
    void doFilterInternal_shouldBypassForActuator() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/actuator/health");
        MockHttpServletResponse response = new MockHttpServletResponse();

        rateLimitingFilter.doFilterInternal(request, response, filterChain);

        verify(rateLimiterService, never()).tryConsume(any(), anyLong(), anyLong());
        verify(rateLimiterService, never()).tryConsumeSliding(any(), anyLong(), anyLong(), any());
        verify(filterChain).doFilter(request, response);
    }

    @Test
    @DisplayName("doFilterInternal: Should apply ai-chat sliding window policy on /api/v1/chat")
    void doFilterInternal_shouldApplyAiChatPolicy() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/api/v1/chat");
        request.addHeader(JwtAuthenticationFilter.USER_ID_HEADER, "user-456");
        MockHttpServletResponse response = new MockHttpServletResponse();

        when(rateLimiterService.tryConsumeSliding(eq("ai-chat:user:user-456"), eq(10L), eq(60L), eq(RateLimitPolicy.FailMode.LOCAL)))
                .thenReturn(new RateLimitResult(true, 10, 9, 60));

        rateLimitingFilter.doFilterInternal(request, response, filterChain);

        assertThat(response.getStatus()).isEqualTo(HttpServletResponse.SC_OK);
        assertThat(response.getHeader("X-RateLimit-Limit")).isEqualTo("10");
        verify(rateLimiterService).tryConsumeSliding("ai-chat:user:user-456", 10, 60, RateLimitPolicy.FailMode.LOCAL);
        verify(filterChain).doFilter(request, response);
    }

    @Test
    @DisplayName("doFilterInternal: Should isolate AI chat bucket from general products bucket")
    void doFilterInternal_shouldIsolateAiChatAndProductsBuckets() throws ServletException, IOException {
        // AI Chat isteği
        MockHttpServletRequest chatReq = new MockHttpServletRequest("POST", "/api/v1/chat");
        chatReq.addHeader(JwtAuthenticationFilter.USER_ID_HEADER, "user-999");
        MockHttpServletResponse chatResp = new MockHttpServletResponse();

        when(rateLimiterService.tryConsumeSliding(eq("ai-chat:user:user-999"), eq(10L), eq(60L), eq(RateLimitPolicy.FailMode.LOCAL)))
                .thenReturn(new RateLimitResult(true, 10, 9, 60));

        rateLimitingFilter.doFilterInternal(chatReq, chatResp, filterChain);
        verify(rateLimiterService).tryConsumeSliding("ai-chat:user:user-999", 10, 60, RateLimitPolicy.FailMode.LOCAL);

        // Genel Ürün Gezintisi isteği (ayrı kova)
        MockHttpServletRequest prodReq = new MockHttpServletRequest("GET", "/api/v1/products");
        prodReq.addHeader(JwtAuthenticationFilter.USER_ID_HEADER, "user-999");
        MockHttpServletResponse prodResp = new MockHttpServletResponse();

        when(rateLimiterService.tryConsume(eq("user:user-999"), eq(60L), eq(60L)))
                .thenReturn(new RateLimitResult(true, 60, 59, 60));

        rateLimitingFilter.doFilterInternal(prodReq, prodResp, filterChain);
        verify(rateLimiterService).tryConsume("user:user-999", 60, 60);
    }

    @Test
    @DisplayName("doFilterInternal: Should match ai-actions policy before ai-chat for actions path")
    void doFilterInternal_shouldMatchAiActionsBeforeAiChat() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/agent/actions/act-123/confirm");
        request.addHeader(JwtAuthenticationFilter.USER_ID_HEADER, "user-456");
        MockHttpServletResponse response = new MockHttpServletResponse();

        when(rateLimiterService.tryConsumeSliding(eq("ai-actions:user:user-456"), eq(20L), eq(60L), eq(RateLimitPolicy.FailMode.LOCAL)))
                .thenReturn(new RateLimitResult(true, 20, 19, 60));

        rateLimitingFilter.doFilterInternal(request, response, filterChain);

        assertThat(response.getStatus()).isEqualTo(HttpServletResponse.SC_OK);
        assertThat(response.getHeader("X-RateLimit-Limit")).isEqualTo("20");
        verify(rateLimiterService).tryConsumeSliding("ai-actions:user:user-456", 20, 60, RateLimitPolicy.FailMode.LOCAL);
    }

    @Test
    @DisplayName("doFilterInternal: Should ignore X-Forwarded-For when trust-forwarded-for is false")
    void doFilterInternal_shouldIgnoreXForwardedForWhenTrustFalse() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/v1/products");
        request.setRemoteAddr("10.0.0.5");
        request.addHeader("X-Forwarded-For", "203.0.113.195, 70.41.3.18");
        MockHttpServletResponse response = new MockHttpServletResponse();

        when(rateLimiterService.tryConsume(eq("ip:10.0.0.5"), eq(10L), eq(60L)))
                .thenReturn(new RateLimitResult(true, 10, 9, 60));

        rateLimitingFilter.doFilterInternal(request, response, filterChain);

        verify(rateLimiterService).tryConsume("ip:10.0.0.5", 10, 60);
    }

    @Test
    @DisplayName("doFilterInternal: Should include policy name in 429 ProblemDetail when AI rate limit is exceeded")
    void doFilterInternal_shouldIncludePolicyInProblemDetail() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/api/v1/chat");
        request.addHeader(JwtAuthenticationFilter.USER_ID_HEADER, "user-789");
        MockHttpServletResponse response = new MockHttpServletResponse();

        when(rateLimiterService.tryConsumeSliding(eq("ai-chat:user:user-789"), eq(10L), eq(60L), eq(RateLimitPolicy.FailMode.LOCAL)))
                .thenReturn(new RateLimitResult(false, 10, 0, 45));

        rateLimitingFilter.doFilterInternal(request, response, filterChain);

        assertThat(response.getStatus()).isEqualTo(429);
        assertThat(response.getContentAsString()).contains("\"policy\":\"ai-chat\"");
        assertThat(response.getContentAsString()).contains("\"retryAfterSeconds\":45");
    }
}
