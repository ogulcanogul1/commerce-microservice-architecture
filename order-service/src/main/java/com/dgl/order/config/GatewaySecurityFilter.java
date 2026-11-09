package com.dgl.order.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.stereotype.Component;
import org.springframework.util.AntPathMatcher;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.List;

/**
 * Security filter that blocks direct microservice access (Gateway Bypass).
 * Requires the trusted 'X-Gateway-Secret' header injected by the API Gateway.
 */
@Slf4j
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 5)
public class GatewaySecurityFilter extends OncePerRequestFilter {

    public static final String GATEWAY_SECRET_HEADER = "X-Gateway-Secret";

    @Value("${gateway.internal.secret:dgl-internal-gateway-secret-token-2026}")
    private String expectedSecret;

    @Value("${gateway.security.enabled:true}")
    private boolean enabled;

    private final AntPathMatcher pathMatcher = new AntPathMatcher();
    private final ObjectMapper objectMapper = new ObjectMapper();

    private static final List<String> EXEMPT_PATHS = List.of(
            "/actuator/**",
            "/v3/api-docs/**",
            "/swagger-ui/**",
            "/swagger-ui.html"
    );

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        if (!enabled || isExemptPath(request.getRequestURI())) {
            filterChain.doFilter(request, response);
            return;
        }

        String receivedSecret = request.getHeader(GATEWAY_SECRET_HEADER);
        boolean secretValid = receivedSecret != null
                && MessageDigest.isEqual(
                        receivedSecret.getBytes(StandardCharsets.UTF_8),
                        expectedSecret.getBytes(StandardCharsets.UTF_8));
        if (!secretValid) {
            log.warn("Blocked direct access attempt to path [{}] from IP [{}]. Missing or invalid {}.",
                    request.getRequestURI(), request.getRemoteAddr(), GATEWAY_SECRET_HEADER);
            writeForbiddenResponse(response);
            return;
        }

        filterChain.doFilter(request, response);
    }

    private boolean isExemptPath(String path) {
        for (String pattern : EXEMPT_PATHS) {
            if (pathMatcher.match(pattern, path)) {
                return true;
            }
        }
        return false;
    }

    private void writeForbiddenResponse(HttpServletResponse response) throws IOException {
        response.setStatus(HttpStatus.FORBIDDEN.value());
        response.setContentType(MediaType.APPLICATION_PROBLEM_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.FORBIDDEN,
                "Direct microservice access denied. Requests must be routed through API Gateway."
        );
        problem.setTitle("Forbidden");
        problem.setType(URI.create("https://api.commerce.com/errors/gateway-bypass-forbidden"));
        problem.setProperty("timestamp", Instant.now().toString());

        response.getWriter().write(objectMapper.writeValueAsString(problem));
    }
}
