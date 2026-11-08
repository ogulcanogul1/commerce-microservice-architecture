package com.dgl.gateway.filter;

import com.dgl.gateway.ratelimit.RateLimitPolicy;
import com.dgl.gateway.ratelimit.RateLimitProperties;
import com.dgl.gateway.ratelimit.RateLimitResult;
import com.dgl.gateway.ratelimit.RateLimiterService;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
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
 * Dağıtık hız sınırlama Gateway filtresi (Rate Limiting Filter).
 * JwtAuthenticationFilter'dan sonra (HIGHEST_PRECEDENCE + 3) konumlanır.
 * Rota bazlı politikaları (RateLimitPolicy) destekler; AI rotalarında kayan pencere (sliding window)
 * ve kova izolasyonu sağlarken, eşleşmeyen genel rotalar için varsayılan kotaları korur.
 */
@Slf4j
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 4)
public class RateLimitingFilter extends OncePerRequestFilter {

    private final RateLimiterService rateLimiterService;
    private final RateLimitProperties rateLimitProperties;
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

    public RateLimitingFilter(RateLimiterService rateLimiterService) {
        this(rateLimiterService, new RateLimitProperties());
    }

    @Autowired
    public RateLimitingFilter(RateLimiterService rateLimiterService, RateLimitProperties rateLimitProperties) {
        this.rateLimiterService = rateLimiterService;
        this.rateLimitProperties = rateLimitProperties != null ? rateLimitProperties : new RateLimitProperties();
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        if (!enabled || HttpMethod.OPTIONS.matches(request.getMethod()) || isExemptPath(request.getRequestURI())) {
            filterChain.doFilter(request, response);
            return;
        }

        String path = request.getRequestURI();
        RateLimitPolicy matchedPolicy = findMatchingPolicy(path);

        String userId = request.getHeader(JwtAuthenticationFilter.USER_ID_HEADER);
        String identity;
        if (userId != null && !userId.isBlank()) {
            identity = "user:" + userId;
        } else {
            identity = "ip:" + getClientIp(request);
        }

        RateLimitResult result;
        String policyName;
        long windowSeconds;

        if (matchedPolicy != null) {
            policyName = matchedPolicy.name();
            String limitKey = policyName + ":" + identity;
            long limit = matchedPolicy.limit();
            windowSeconds = matchedPolicy.windowSeconds();

            if (matchedPolicy.algorithm() == RateLimitPolicy.Algorithm.SLIDING_WINDOW) {
                result = rateLimiterService.tryConsumeSliding(limitKey, limit, windowSeconds, matchedPolicy.failMode());
            } else {
                result = rateLimiterService.tryConsume(limitKey, limit, windowSeconds);
            }
        } else {
            policyName = "default";
            String limitKey = identity;
            long limit;
            if (userId != null && !userId.isBlank()) {
                limit = authenticatedLimit;
                windowSeconds = authenticatedWindowSeconds;
            } else {
                limit = anonymousLimit;
                windowSeconds = anonymousWindowSeconds;
            }
            result = rateLimiterService.tryConsume(limitKey, limit, windowSeconds);
        }

        response.setHeader("X-RateLimit-Limit", String.valueOf(result.limit()));
        response.setHeader("X-RateLimit-Remaining", String.valueOf(result.remaining()));
        response.setHeader("X-RateLimit-Reset", String.valueOf(result.resetSeconds()));

        if (!result.allowed()) {
            log.warn("Rate limit exceeded for policy [{}] key [{}]: {}/{} within {}s",
                    policyName, identity, result.limit(), result.limit(), windowSeconds);
            writeRateLimitExceededResponse(response, result, policyName);
            return;
        }

        filterChain.doFilter(request, response);
    }

    private RateLimitPolicy findMatchingPolicy(String path) {
        if (rateLimitProperties != null && rateLimitProperties.getPolicies() != null) {
            for (RateLimitPolicy policy : rateLimitProperties.getPolicies()) {
                if (policy.pathPatterns() != null) {
                    for (String pattern : policy.pathPatterns()) {
                        if (pathMatcher.match(pattern, path)) {
                            return policy;
                        }
                    }
                }
            }
        }
        return null;
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
        return request.getRemoteAddr();
    }

    private void writeRateLimitExceededResponse(
            HttpServletResponse response,
            RateLimitResult result,
            String policyName) throws IOException {

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
        problem.setProperty("policy", policyName);
        problem.setProperty("retryAfterSeconds", result.resetSeconds());
        problem.setProperty("timestamp", Instant.now().toString());

        response.getWriter().write(objectMapper.writeValueAsString(problem));
    }
}
