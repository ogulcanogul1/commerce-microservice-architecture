package com.dgl.gateway.filter;

import com.dgl.gateway.security.JwtValidator;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.core.context.SecurityContextHolder;

import java.io.IOException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class JwtAuthenticationFilterTest {

    @Mock
    private JwtValidator jwtValidator;

    @Mock
    private FilterChain filterChain;

    @Mock
    private Claims claims;

    private JwtAuthenticationFilter filter;

    @BeforeEach
    void setUp() {
        filter = new JwtAuthenticationFilter(jwtValidator);
        SecurityContextHolder.clearContext();
    }

    @Test
    @DisplayName("Public path (/api/v1/auth/login) should pass through without token")
    void publicPath_ShouldPassWithoutToken() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/api/v1/auth/login");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, filterChain);

        verify(filterChain).doFilter(request, response);
        verifyNoInteractions(jwtValidator);
    }

    @Test
    @DisplayName("Public GET /api/v1/products should pass through without token")
    void publicGetProducts_ShouldPassWithoutToken() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/v1/products/123");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, filterChain);

        verify(filterChain).doFilter(request, response);
        verifyNoInteractions(jwtValidator);
    }

    @Test
    @DisplayName("OPTIONS request (CORS) should pass through without token")
    void corsOptions_ShouldPassWithoutToken() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest("OPTIONS", "/api/v1/orders");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, filterChain);

        verify(filterChain).doFilter(request, response);
        verifyNoInteractions(jwtValidator);
    }

    @Test
    @DisplayName("Protected path (POST /api/v1/orders) without Authorization header should return 401")
    void protectedPath_WhenMissingAuthHeader_ShouldReturn401() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/api/v1/orders");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, filterChain);

        assertThat(response.getStatus()).isEqualTo(401);
        assertThat(response.getContentAsString()).contains("Authorization header with Bearer token is required");
        verify(filterChain, never()).doFilter(any(), any());
    }

    @Test
    @DisplayName("Protected path with invalid token should return 401")
    void protectedPath_WhenInvalidToken_ShouldReturn401() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/api/v1/orders");
        request.addHeader("Authorization", "Bearer invalid-token");
        MockHttpServletResponse response = new MockHttpServletResponse();

        when(jwtValidator.validateAndExtractClaims("invalid-token"))
                .thenThrow(new JwtException("Signature mismatch"));

        filter.doFilter(request, response, filterChain);

        assertThat(response.getStatus()).isEqualTo(401);
        assertThat(response.getContentAsString()).contains("Invalid or expired JWT token");
        verify(filterChain, never()).doFilter(any(), any());
    }

    @Test
    @DisplayName("Protected path with valid token should set headers and authenticate")
    void protectedPath_WhenValidToken_ShouldInjectUserHeadersAndProceed() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/api/v1/orders");
        request.addHeader("Authorization", "Bearer valid-token");
        MockHttpServletResponse response = new MockHttpServletResponse();

        when(jwtValidator.validateAndExtractClaims("valid-token")).thenReturn(claims);
        when(claims.getSubject()).thenReturn("user-uuid-123");
        when(claims.get("email", String.class)).thenReturn("user@example.com");
        when(claims.get("role", String.class)).thenReturn("ROLE_CUSTOMER");

        ArgumentCaptor<HttpServletRequest> requestCaptor = ArgumentCaptor.forClass(HttpServletRequest.class);

        filter.doFilter(request, response, filterChain);

        verify(filterChain).doFilter(requestCaptor.capture(), eq(response));

        HttpServletRequest forwardedRequest = requestCaptor.getValue();
        assertThat(forwardedRequest.getHeader("X-User-Id")).isEqualTo("user-uuid-123");
        assertThat(forwardedRequest.getHeader("X-User-Email")).isEqualTo("user@example.com");
        assertThat(forwardedRequest.getHeader("X-User-Roles")).isEqualTo("ROLE_CUSTOMER");
    }
}
