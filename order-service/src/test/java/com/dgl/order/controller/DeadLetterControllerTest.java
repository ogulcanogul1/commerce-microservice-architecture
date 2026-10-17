package com.dgl.order.controller;

import com.dgl.order.domain.DeadLetterStatus;
import com.dgl.order.dto.response.DeadLetterMessageResponse;
import com.dgl.order.exception.AccessDeniedException;
import com.dgl.order.service.DeadLetterService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class DeadLetterControllerTest {

    @Mock
    private DeadLetterService deadLetterService;

    @InjectMocks
    private DeadLetterController controller;

    private UUID messageId;
    private DeadLetterMessageResponse mockResponse;

    @BeforeEach
    void setUp() {
        messageId = UUID.randomUUID();
        mockResponse = new DeadLetterMessageResponse(
                messageId,
                "orders.created",
                "ORD-1",
                "{}",
                "Error",
                DeadLetterStatus.PENDING,
                Instant.now(),
                null
        );
    }

    @Test
    @DisplayName("getDeadLetters: Should return 200 OK when requested by Admin")
    void getDeadLetters_shouldReturnOkForAdmin() {
        PageRequest pageRequest = PageRequest.of(0, 10);
        Page<DeadLetterMessageResponse> page = new PageImpl<>(List.of(mockResponse));
        when(deadLetterService.getDeadLetters(DeadLetterStatus.PENDING, pageRequest)).thenReturn(page);

        ResponseEntity<Page<DeadLetterMessageResponse>> response = controller.getDeadLetters(
                DeadLetterStatus.PENDING, "ROLE_ADMIN", pageRequest);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isSameAs(page);
    }

    @Test
    @DisplayName("getDeadLetters: Should throw AccessDeniedException when requested by non-admin")
    void getDeadLetters_shouldThrowForNonAdmin() {
        PageRequest pageRequest = PageRequest.of(0, 10);

        assertThatThrownBy(() -> controller.getDeadLetters(
                DeadLetterStatus.PENDING, "ROLE_CUSTOMER", pageRequest))
                .isInstanceOf(AccessDeniedException.class)
                .hasMessageContaining("Access denied");

        verifyNoInteractions(deadLetterService);
    }

    @Test
    @DisplayName("replayDeadLetter: Should replay message when requested by Admin")
    void replayDeadLetter_shouldReplayForAdmin() {
        when(deadLetterService.replayDeadLetter(messageId)).thenReturn(mockResponse);

        ResponseEntity<DeadLetterMessageResponse> response = controller.replayDeadLetter(messageId, "ROLE_ADMIN");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        verify(deadLetterService).replayDeadLetter(messageId);
    }

    @Test
    @DisplayName("discardDeadLetter: Should discard message when requested by Admin")
    void discardDeadLetter_shouldDiscardForAdmin() {
        when(deadLetterService.discardDeadLetter(messageId)).thenReturn(mockResponse);

        ResponseEntity<DeadLetterMessageResponse> response = controller.discardDeadLetter(messageId, "ROLE_ADMIN");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        verify(deadLetterService).discardDeadLetter(messageId);
    }
}
