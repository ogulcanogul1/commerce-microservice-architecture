package com.dgl.gateway.filter;

import com.dgl.gateway.ratelimit.RateLimitResult;
import com.dgl.gateway.ratelimit.RateLimiterService;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.stereotype.Component;
import org.springframework.util.AntPathMatcher;
import org.springframework.web.filter.OncePerRequestFilter;
import tools.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;

/**
 * Gateway filter for distributed rate limiting across clients and authenticated users.
 * Sits after JwtAuthenticationFilter (HIGHEST_PRECEDENCE + 3) so that authenticated user IDs
 * are leveraged for tiered quotas, while falling back to client IP for anonymous requests.
 */
@Slf4j
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 3)
@RequiredArgsConstructor
public class RateLimitingFilter extends OncePerRequestFilter {

    private final RateLimiterService rateLimiterService;
    private final AntPathMatcher pathMatcher = new AntPathMatcher();
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Value("${rate-limiter.enabled:true}")
    private boolean enabled;

    @Value("${rate-limiter.anonymous.limit:10}")
    private long anonymousLimit;

    @Value("${rate-limiter.anonymous.window-seconds:60}")
    private long anonymousWindowSeconds;

    @Value("${rate-limiter.authenticated.limit:60}")
    private long authenticatedLimit;

    @Value("${rate-limiter.authenticated.window-seconds:60}")
    private long authenticatedWindowSeconds;

    private static final List<String> EXEMPT_PATHS = List.of(
            "/actuator/**",
            "/fallback/**"
    );

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        if (!enabled || HttpMethod.OPTIONS.matches(request.getMethod()) || isExemptPath(request.getRequestURI())) {
            filterChain.doFilter(request, response);
            return;
        }

        String userId = request.getHeader(JwtAuthenticationFilter.USER_ID_HEADER);
        String limitKey;
        long limit;
        long windowSeconds;

        if (userId != null && !userId.isBlank()) {
            limitKey = "user:" + userId;
            limit = authenticatedLimit;
            windowSeconds = authenticatedWindowSeconds;
        } else {
            limitKey = "ip:" + getClientIp(request);
            limit = anonymousLimit;
            windowSeconds = anonymousWindowSeconds;
        }

        RateLimitResult result = rateLimiterService.tryConsume(limitKey, limit, windowSeconds);

        response.setHeader("X-RateLimit-Limit", String.valueOf(result.limit()));
        response.setHeader("X-RateLimit-Remaining", String.valueOf(result.remaining()));
        response.setHeader("X-RateLimit-Reset", String.valueOf(result.resetSeconds()));

        if (!result.allowed()) {
            log.warn("Rate limit exceeded for key [{}]: {}/{} within {}s",
                    limitKey, result.limit(), result.limit(), windowSeconds);
            writeRateLimitExceededResponse(response, result);
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

    private String getClientIp(HttpServletRequest request) {
        String xForwardedFor = request.getHeader("X-Forwarded-For");
        if (xForwardedFor != null && !xForwardedFor.isBlank()) {
            return xForwardedFor.split(",")[0].trim();
        }
        return request.getRemoteAddr();
    }

    private void writeRateLimitExceededResponse(HttpServletResponse response, RateLimitResult result) throws IOException {
        response.setStatus(HttpStatus.TOO_MANY_REQUESTS.value());
        response.setHeader("Retry-After", String.valueOf(result.resetSeconds()));
        response.setContentType(MediaType.APPLICATION_PROBLEM_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.TOO_MANY_REQUESTS,
                "Rate limit exceeded. Maximum allowed: " + result.limit() + " requests per window. Try again in " + result.resetSeconds() + " seconds."
        );
        problem.setTitle("Too Many Requests");
        problem.setType(URI.create("https://api.commerce.com/errors/rate-limit-exceeded"));
        problem.setProperty("retryAfterSeconds", result.resetSeconds());
        problem.setProperty("timestamp", Instant.now().toString());

        response.getWriter().write(objectMapper.writeValueAsString(problem));
    }
}
