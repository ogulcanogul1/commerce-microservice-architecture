package com.dgl.gateway.filter;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import java.io.IOException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

class AiRequestSizeFilterTest {

    private final AiRequestSizeFilter filter = new AiRequestSizeFilter();

    @Test
    @DisplayName("AI rotasında 64 KB üzerindeki POST isteği 413 Payload Too Large ile reddedilmelidir")
    void shouldRejectOversizedAiPostRequest() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/agent/chat");
        // 70 KB (> 64 KB = 65536 bayt)
        request.setContent(new byte[70000]);
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain filterChain = mock(FilterChain.class);

        filter.doFilterInternal(request, response, filterChain);

        assertThat(response.getStatus()).isEqualTo(HttpStatus.PAYLOAD_TOO_LARGE.value());
        assertThat(response.getContentType()).contains("application/problem+json");
        assertThat(response.getContentAsString()).contains("Payload Too Large");
        assertThat(response.getContentAsString()).contains("65536");
        verifyNoInteractions(filterChain);
    }

    @Test
    @DisplayName("AI rotasında 64 KB altındaki normal POST isteği filtreden geçmelidir")
    void shouldAllowNormalSizeAiPostRequest() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/agent/chat");
        // 10 KB
        request.setContent(new byte[10240]);
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain filterChain = mock(FilterChain.class);

        filter.doFilterInternal(request, response, filterChain);

        assertThat(response.getStatus()).isEqualTo(HttpStatus.OK.value());
        verify(filterChain, times(1)).doFilter(request, response);
    }

    @Test
    @DisplayName("AI rotasında GET istekleri gövde boyutu kontrolüne takılmadan geçmelidir")
    void shouldAllowGetRequestsOnAiPath() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/agent/health");
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain filterChain = mock(FilterChain.class);

        filter.doFilterInternal(request, response, filterChain);

        verify(filterChain, times(1)).doFilter(request, response);
    }

    @Test
    @DisplayName("AI rotası olmayan yollar (örn: /api/v1/products) filtreden etkilenmemelidir")
    void shouldIgnoreNonAiPaths() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/api/v1/products");
        request.setContent(new byte[100000]);
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain filterChain = mock(FilterChain.class);

        filter.doFilterInternal(request, response, filterChain);

        verify(filterChain, times(1)).doFilter(request, response);
    }

    @Test
    @DisplayName("AI rotasında 64 KB üzerindeki Chunked POST isteği 413 Payload Too Large ile reddedilmelidir")
    void shouldRejectOversizedChunkedAiPostRequest() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/agent/chat") {
            @Override
            public long getContentLengthLong() {
                return -1;
            }
        };
        request.setContent(new byte[70000]);
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain filterChain = mock(FilterChain.class);

        filter.doFilterInternal(request, response, filterChain);

        assertThat(response.getStatus()).isEqualTo(HttpStatus.PAYLOAD_TOO_LARGE.value());
        assertThat(response.getContentType()).contains("application/problem+json");
        assertThat(response.getContentAsString()).contains("Payload Too Large");
        assertThat(response.getContentAsString()).contains("65536");
        verifyNoInteractions(filterChain);
    }

    @Test
    @DisplayName("AI rotasında 64 KB altındaki Chunked POST isteği sarmalanarak filtreden geçmeli ve okunabilir olmalıdır")
    void shouldAllowNormalSizeChunkedAiPostRequest() throws ServletException, IOException {
        byte[] expectedContent = "{\"message\":\"chunked hello\"}".getBytes(java.nio.charset.StandardCharsets.UTF_8);
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/agent/chat") {
            @Override
            public long getContentLengthLong() {
                return -1;
            }
        };
        request.setContent(expectedContent);
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain filterChain = mock(FilterChain.class);

        doAnswer(invocation -> {
            jakarta.servlet.http.HttpServletRequest req = invocation.getArgument(0);
            byte[] readBytes = req.getInputStream().readAllBytes();
            assertThat(readBytes).isEqualTo(expectedContent);
            return null;
        }).when(filterChain).doFilter(any(), any());

        filter.doFilterInternal(request, response, filterChain);

        assertThat(response.getStatus()).isEqualTo(HttpStatus.OK.value());
        verify(filterChain, times(1)).doFilter(any(), eq(response));
    }
}
