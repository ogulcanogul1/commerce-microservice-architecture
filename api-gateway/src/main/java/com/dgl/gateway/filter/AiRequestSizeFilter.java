package com.dgl.gateway.filter;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.extern.slf4j.Slf4j;
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
 * AI rotaları için istek gövdesi boyutu (Content-Length) filtresi.
 *
 * Güvenlik & DDoS Koruması:
 * 64 KB (65536 bayt) üzerindeki istekleri downstream AI servisine iletmeden
 * doğrudan Gateway seviyesinde 413 Payload Too Large ile reddeder.
 */
@Slf4j
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 2)
public class AiRequestSizeFilter extends OncePerRequestFilter {

    public static final long MAX_BODY_BYTES = 65536L; // 64 KB

    private static final List<String> AI_PATH_PATTERNS = List.of(
            "/agent/**",
            "/api/v1/chat/**",
            "/rag/**"
    );

    private final AntPathMatcher pathMatcher = new AntPathMatcher();
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {

        // Yalnızca POST isteklerinde ve AI rotalarında kontrol et
        if (HttpMethod.POST.matches(request.getMethod()) && isAiPath(request.getRequestURI())) {
            long contentLength = request.getContentLengthLong();

            if (contentLength > MAX_BODY_BYTES) {
                log.warn("AI payload size limit exceeded: {} bytes > {} bytes for URI: {}",
                        contentLength, MAX_BODY_BYTES, request.getRequestURI());

                ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                        HttpStatus.PAYLOAD_TOO_LARGE,
                        "İstek gövdesi izin verilen maksimum boyuttan büyük (" + contentLength + " > " + MAX_BODY_BYTES + " bayt)."
                );
                problem.setTitle("Payload Too Large");
                problem.setType(URI.create("https://api.commerce.com/errors/payload-too-large"));
                problem.setProperty("timestamp", Instant.now());
                problem.setProperty("retryable", false);

                response.setStatus(HttpStatus.PAYLOAD_TOO_LARGE.value());
                response.setContentType(MediaType.APPLICATION_PROBLEM_JSON_VALUE);
                response.setCharacterEncoding(StandardCharsets.UTF_8.name());
                response.getWriter().write(objectMapper.writeValueAsString(problem));
                return;
            }
        }

        filterChain.doFilter(request, response);
    }

    private boolean isAiPath(String requestUri) {
        for (String pattern : AI_PATH_PATTERNS) {
            if (pathMatcher.match(pattern, requestUri)) {
                return true;
            }
        }
        return false;
    }
}
