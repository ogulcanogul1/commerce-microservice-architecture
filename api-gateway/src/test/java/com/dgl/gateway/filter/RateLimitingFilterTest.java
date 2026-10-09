package com.dgl.gateway.filter;

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

import static org.assertj.core.api.Assertions.assertThat;
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
        verify(filterChain, never()).doFilter(any(), any());
    }

    @Test
    @DisplayName("doFilterInternal: Should apply higher authenticated quota when X-User-Id is present")
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
        verify(filterChain).doFilter(request, response);
    }
}
