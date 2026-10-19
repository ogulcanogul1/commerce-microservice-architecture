package com.dgl.gateway.filter;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;
import jakarta.servlet.http.HttpServletResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.*;

/**
 * Filter that attaches the trusted internal gateway secret (X-Gateway-Secret)
 * to all downstream proxied requests. Overwrites any client-supplied header to prevent spoofing.
 */
@Slf4j
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 1)
public class GatewayInternalSecurityFilter extends OncePerRequestFilter {

    public static final String GATEWAY_SECRET_HEADER = "X-Gateway-Secret";

    @Value("${gateway.internal.secret:dgl-internal-gateway-secret-token-2026}")
    private String gatewaySecret;

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        GatewaySecretRequestWrapper wrappedRequest = new GatewaySecretRequestWrapper(request, gatewaySecret);
        filterChain.doFilter(wrappedRequest, response);
    }

    private static class GatewaySecretRequestWrapper extends HttpServletRequestWrapper {

        private final String secret;

        public GatewaySecretRequestWrapper(HttpServletRequest request, String secret) {
            super(request);
            this.secret = secret;
        }

        @Override
        public String getHeader(String name) {
            if (GATEWAY_SECRET_HEADER.equalsIgnoreCase(name)) {
                return secret;
            }
            return super.getHeader(name);
        }

        @Override
        public Enumeration<String> getHeaders(String name) {
            if (GATEWAY_SECRET_HEADER.equalsIgnoreCase(name)) {
                return Collections.enumeration(List.of(secret));
            }
            return super.getHeaders(name);
        }

        @Override
        public Enumeration<String> getHeaderNames() {
            Set<String> headerNames = new LinkedHashSet<>();
            Enumeration<String> baseNames = super.getHeaderNames();
            while (baseNames.hasMoreElements()) {
                headerNames.add(baseNames.nextElement());
            }
            headerNames.add(GATEWAY_SECRET_HEADER);
            return Collections.enumeration(headerNames);
        }
    }
}
