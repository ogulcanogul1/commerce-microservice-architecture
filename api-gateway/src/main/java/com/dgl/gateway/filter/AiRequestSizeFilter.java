package com.dgl.gateway.filter;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ReadListener;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletInputStream;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;
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

import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
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
                sendPayloadTooLarge(response, "İstek gövdesi izin verilen maksimum boyuttan büyük (" + contentLength + " > " + MAX_BODY_BYTES + " bayt).");
                return;
            }

            // Chunked transfer-encoding veya Content-Length başlığı bulunmayan akışlar (contentLength < 0)
            if (contentLength < 0) {
                byte[] body = request.getInputStream().readNBytes((int) MAX_BODY_BYTES + 1);
                if (body.length > MAX_BODY_BYTES) {
                    log.warn("AI chunked payload size limit exceeded (> {} bytes) for URI: {}",
                            MAX_BODY_BYTES, request.getRequestURI());
                    sendPayloadTooLarge(response, "İstek gövdesi izin verilen maksimum boyuttan büyük (> " + MAX_BODY_BYTES + " bayt).");
                    return;
                }

                // Limit aşılmadıysa, okunan gövdeyi downstream'in tekrar okuyabilmesi için sarmala
                CachedBodyHttpServletRequest wrappedRequest = new CachedBodyHttpServletRequest(request, body);
                filterChain.doFilter(wrappedRequest, response);
                return;
            }
        }

        filterChain.doFilter(request, response);
    }

    private void sendPayloadTooLarge(HttpServletResponse response, String detail) throws IOException {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.PAYLOAD_TOO_LARGE,
                detail
        );
        problem.setTitle("Payload Too Large");
        problem.setType(URI.create("https://api.commerce.com/errors/payload-too-large"));
        problem.setProperty("timestamp", Instant.now());
        problem.setProperty("retryable", false);

        response.setStatus(HttpStatus.PAYLOAD_TOO_LARGE.value());
        response.setContentType(MediaType.APPLICATION_PROBLEM_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.getWriter().write(objectMapper.writeValueAsString(problem));
    }

    private static class CachedBodyHttpServletRequest extends HttpServletRequestWrapper {
        private final byte[] cachedBody;

        public CachedBodyHttpServletRequest(HttpServletRequest request, byte[] cachedBody) {
            super(request);
            this.cachedBody = cachedBody;
        }

        @Override
        public ServletInputStream getInputStream() {
            ByteArrayInputStream bais = new ByteArrayInputStream(cachedBody);
            return new ServletInputStream() {
                @Override
                public boolean isFinished() {
                    return bais.available() == 0;
                }

                @Override
                public boolean isReady() {
                    return true;
                }

                @Override
                public void setReadListener(ReadListener readListener) {
                }

                @Override
                public int read() {
                    return bais.read();
                }

                @Override
                public int read(byte[] b, int off, int len) {
                    return bais.read(b, off, len);
                }
            };
        }

        @Override
        public BufferedReader getReader() {
            return new BufferedReader(new InputStreamReader(getInputStream(), StandardCharsets.UTF_8));
        }

        @Override
        public int getContentLength() {
            return cachedBody.length;
        }

        @Override
        public long getContentLengthLong() {
            return cachedBody.length;
        }
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
