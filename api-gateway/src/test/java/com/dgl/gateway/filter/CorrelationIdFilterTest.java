package com.dgl.gateway.filter;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import java.io.IOException;

import static org.assertj.core.api.Assertions.assertThat;

class CorrelationIdFilterTest {

    private final CorrelationIdFilter filter = new CorrelationIdFilter();

    @Test
    @DisplayName("doFilterInternal should generate a new UUID correlationId when none is provided in request")
    void doFilterInternal_WhenNoCorrelationIdHeader_ShouldGenerateNew() throws ServletException, IOException {
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();

        final String[] capturedIdInChain = new String[1];
        FilterChain chain = (req, res) -> {
            capturedIdInChain[0] = ((HttpServletRequest) req).getHeader(CorrelationIdFilter.CORRELATION_ID_HEADER);
        };

        filter.doFilterInternal(request, response, chain);

        String responseHeader = response.getHeader(CorrelationIdFilter.CORRELATION_ID_HEADER);
        assertThat(responseHeader).isNotNull().isNotBlank();
        assertThat(capturedIdInChain[0]).isEqualTo(responseHeader);
    }

    @Test
    @DisplayName("doFilterInternal should preserve existing correlationId when provided in request")
    void doFilterInternal_WhenCorrelationIdHeaderPresent_ShouldPreserveExisting() throws ServletException, IOException {
        String existingId = "existing-uuid-12345";
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader(CorrelationIdFilter.CORRELATION_ID_HEADER, existingId);
        MockHttpServletResponse response = new MockHttpServletResponse();

        final String[] capturedIdInChain = new String[1];
        FilterChain chain = (req, res) -> {
            capturedIdInChain[0] = ((HttpServletRequest) req).getHeader(CorrelationIdFilter.CORRELATION_ID_HEADER);
        };

        filter.doFilterInternal(request, response, chain);

        String responseHeader = response.getHeader(CorrelationIdFilter.CORRELATION_ID_HEADER);
        assertThat(responseHeader).isEqualTo(existingId);
        assertThat(capturedIdInChain[0]).isEqualTo(existingId);
    }
}
