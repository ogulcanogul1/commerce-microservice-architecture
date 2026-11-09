package com.dgl.shipping.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
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
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class GatewaySecurityFilterTest {

    @Mock
    private FilterChain filterChain;

    @InjectMocks
    private GatewaySecurityFilter gatewaySecurityFilter;

    private static final String VALID_SECRET = "test-internal-gateway-secret-token";

    @BeforeEach
    void setUp() {
        ReflectionTestUtils.setField(gatewaySecurityFilter, "expectedSecret", VALID_SECRET);
        ReflectionTestUtils.setField(gatewaySecurityFilter, "enabled", true);
    }

    @Test
    @DisplayName("Should allow request when path is exempt (e.g. /actuator/health)")
    void shouldAllowExemptPath() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/actuator/health");
        MockHttpServletResponse response = new MockHttpServletResponse();

        gatewaySecurityFilter.doFilterInternal(request, response, filterChain);

        verify(filterChain).doFilter(request, response);
        assertThat(response.getStatus()).isEqualTo(200);
    }

    @Test
    @DisplayName("Should allow request when valid X-Gateway-Secret header is present")
    void shouldAllowWhenValidSecretProvided() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/v1/shipments/track/TRK-100");
        request.addHeader(GatewaySecurityFilter.GATEWAY_SECRET_HEADER, VALID_SECRET);
        MockHttpServletResponse response = new MockHttpServletResponse();

        gatewaySecurityFilter.doFilterInternal(request, response, filterChain);

        verify(filterChain).doFilter(request, response);
        assertThat(response.getStatus()).isEqualTo(200);
    }

    @Test
    @DisplayName("Should reject request with 403 Forbidden when X-Gateway-Secret header is missing")
    void shouldBlockWhenSecretMissing() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/v1/shipments/track/TRK-100");
        MockHttpServletResponse response = new MockHttpServletResponse();

        gatewaySecurityFilter.doFilterInternal(request, response, filterChain);

        verify(filterChain, never()).doFilter(any(), any());
        assertThat(response.getStatus()).isEqualTo(403);
        assertThat(response.getContentAsString()).contains("Direct microservice access denied");
    }

    @Test
    @DisplayName("Should reject request with 403 Forbidden when X-Gateway-Secret header is invalid")
    void shouldBlockWhenSecretInvalid() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/v1/shipments/track/TRK-100");
        request.addHeader(GatewaySecurityFilter.GATEWAY_SECRET_HEADER, "wrong-secret-token");
        MockHttpServletResponse response = new MockHttpServletResponse();

        gatewaySecurityFilter.doFilterInternal(request, response, filterChain);

        verify(filterChain, never()).doFilter(any(), any());
        assertThat(response.getStatus()).isEqualTo(403);
        assertThat(response.getContentAsString()).contains("Direct microservice access denied");
    }

    @Test
    @DisplayName("Should reject request with 403 Forbidden when secret has different length")
    void shouldBlockWhenSecretHasDifferentLength() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/v1/shipments/track/TRK-100");
        request.addHeader(GatewaySecurityFilter.GATEWAY_SECRET_HEADER, "short");
        MockHttpServletResponse response = new MockHttpServletResponse();

        gatewaySecurityFilter.doFilterInternal(request, response, filterChain);

        verify(filterChain, never()).doFilter(any(), any());
        assertThat(response.getStatus()).isEqualTo(403);
    }

    @Test
    @DisplayName("Should allow all requests when filter is disabled via configuration")
    void shouldAllowWhenDisabled() throws ServletException, IOException {
        ReflectionTestUtils.setField(gatewaySecurityFilter, "enabled", false);
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/v1/shipments/track/TRK-100");
        MockHttpServletResponse response = new MockHttpServletResponse();

        gatewaySecurityFilter.doFilterInternal(request, response, filterChain);

        verify(filterChain).doFilter(request, response);
    }
}
