package com.dgl.gateway.filter;

import com.dgl.gateway.security.JwtValidator;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.util.AntPathMatcher;
import org.springframework.web.filter.OncePerRequestFilter;
import tools.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.*;

@Slf4j
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 2)
@RequiredArgsConstructor
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    private final JwtValidator jwtValidator;
    private final AntPathMatcher pathMatcher = new AntPathMatcher();
    private final ObjectMapper objectMapper = new ObjectMapper();

    public static final String USER_ID_HEADER = "X-User-Id";
    public static final String USER_EMAIL_HEADER = "X-User-Email";
    public static final String USER_ROLES_HEADER = "X-User-Roles";

    private static final List<String> PUBLIC_PATHS = List.of(
            "/actuator/**",
            "/fallback/**",
            "/api/v1/auth/**"
    );

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {

        String path = request.getRequestURI();
        String method = request.getMethod();

        // 1. CORS Preflight
        if (HttpMethod.OPTIONS.matches(method)) {
            filterChain.doFilter(request, response);
            return;
        }

        // 2. Public paths check
        if (isPublicPath(path, method)) {
            filterChain.doFilter(request, response);
            return;
        }

        // 3. Extract Authorization header
        String authHeader = request.getHeader("Authorization");
        if (authHeader == null || !authHeader.startsWith("Bearer ")) {
            log.warn("Missing or invalid Authorization header for protected path: {} {}", method, path);
            writeUnauthorizedResponse(response, "Authorization header with Bearer token is required");
            return;
        }

        String token = authHeader.substring(7).trim();

        // 4. Validate token and extract claims
        try {
            Claims claims = jwtValidator.validateAndExtractClaims(token);
            String userId = claims.getSubject();
            String email = claims.get("email", String.class);
            String role = claims.get("role", String.class);

            if (role == null || role.isBlank()) {
                role = "ROLE_CUSTOMER";
            }

            UsernamePasswordAuthenticationToken authentication = new UsernamePasswordAuthenticationToken(
                    userId,
                    null,
                    List.of(new SimpleGrantedAuthority(role))
            );
            SecurityContextHolder.getContext().setAuthentication(authentication);

            // 5. Wrap request with user context headers for downstream propagation
            UserClaimsRequestWrapper wrappedRequest = new UserClaimsRequestWrapper(request, userId, email, role);
            filterChain.doFilter(wrappedRequest, response);

        } catch (JwtException | IllegalArgumentException ex) {
            log.warn("JWT validation failed for path {}: {}", path, ex.getMessage());
            writeUnauthorizedResponse(response, "Invalid or expired JWT token: " + ex.getMessage());
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    private boolean isPublicPath(String path, String method) {
        for (String pattern : PUBLIC_PATHS) {
            if (pathMatcher.match(pattern, path)) {
                return true;
            }
        }

        // Public read-only catalog browsing
        if (HttpMethod.GET.matches(method)) {
            if (pathMatcher.match("/api/v1/products/**", path) || pathMatcher.match("/api/v1/categories/**", path)) {
                return true;
            }
        }

        return false;
    }

    private void writeUnauthorizedResponse(HttpServletResponse response, String detail) throws IOException {
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setContentType(MediaType.APPLICATION_PROBLEM_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(HttpStatus.UNAUTHORIZED, detail);
        problem.setTitle("Unauthorized");
        problem.setType(URI.create("https://api.commerce.com/errors/unauthorized"));
        problem.setProperty("timestamp", Instant.now().toString());

        response.getWriter().write(objectMapper.writeValueAsString(problem));
    }

    public static class UserClaimsRequestWrapper extends HttpServletRequestWrapper {

        private final Map<String, String> customHeaders = new HashMap<>();

        public UserClaimsRequestWrapper(HttpServletRequest request, String userId, String email, String role) {
            super(request);
            if (userId != null) customHeaders.put(USER_ID_HEADER, userId);
            if (email != null) customHeaders.put(USER_EMAIL_HEADER, email);
            if (role != null) customHeaders.put(USER_ROLES_HEADER, role);
        }

        @Override
        public String getHeader(String name) {
            for (Map.Entry<String, String> entry : customHeaders.entrySet()) {
                if (entry.getKey().equalsIgnoreCase(name)) {
                    return entry.getValue();
                }
            }
            return super.getHeader(name);
        }

        @Override
        public Enumeration<String> getHeaders(String name) {
            for (Map.Entry<String, String> entry : customHeaders.entrySet()) {
                if (entry.getKey().equalsIgnoreCase(name)) {
                    return Collections.enumeration(List.of(entry.getValue()));
                }
            }
            return super.getHeaders(name);
        }

        @Override
        public Enumeration<String> getHeaderNames() {
            Set<String> names = new LinkedHashSet<>();
            Enumeration<String> baseNames = super.getHeaderNames();
            while (baseNames.hasMoreElements()) {
                names.add(baseNames.nextElement());
            }
            names.addAll(customHeaders.keySet());
            return Collections.enumeration(names);
        }
    }
}
