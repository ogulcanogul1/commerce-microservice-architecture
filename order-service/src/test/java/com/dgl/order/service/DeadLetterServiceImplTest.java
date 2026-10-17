package com.dgl.order.service;

import com.dgl.order.domain.DeadLetterMessage;
import com.dgl.order.domain.DeadLetterStatus;
import com.dgl.order.dto.response.DeadLetterMessageResponse;
import com.dgl.order.repository.DeadLetterMessageRepository;
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
import org.springframework.kafka.core.KafkaTemplate;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class DeadLetterServiceImplTest {

    @Mock
    private DeadLetterMessageRepository repository;

    @Mock
    private KafkaTemplate<String, String> kafkaTemplate;

    @InjectMocks
    private DeadLetterServiceImpl deadLetterService;

    private UUID messageId;
    private DeadLetterMessage mockMessage;

    @BeforeEach
    void setUp() {
        messageId = UUID.randomUUID();
        mockMessage = DeadLetterMessage.builder()
                .id(messageId)
                .originalTopic("orders.created")
                .originalKey("ORD-123")
                .payload("{\"orderId\":\"" + messageId + "\"}")
                .exceptionMessage("Deserialization failed")
                .status(DeadLetterStatus.PENDING)
                .createdAt(Instant.now())
                .build();
    }

    @Test
    @DisplayName("getDeadLetters: Should retrieve paginated dead letter messages")
    void getDeadLetters_shouldReturnPage() {
        PageRequest pageRequest = PageRequest.of(0, 10);
        Page<DeadLetterMessage> page = new PageImpl<>(List.of(mockMessage));

        when(repository.findByStatus(DeadLetterStatus.PENDING, pageRequest)).thenReturn(page);

        Page<DeadLetterMessageResponse> result = deadLetterService.getDeadLetters(DeadLetterStatus.PENDING, pageRequest);

        assertThat(result.getContent()).hasSize(1);
        assertThat(result.getContent().get(0).id()).isEqualTo(messageId);
        assertThat(result.getContent().get(0).originalTopic()).isEqualTo("orders.created");
    }

    @Test
    @DisplayName("replayDeadLetter: Should send message to original topic and mark as REPLAYED")
    void replayDeadLetter_shouldPublishToKafkaAndMarkReplayed() {
        when(repository.findById(messageId)).thenReturn(Optional.of(mockMessage));
        when(repository.save(any(DeadLetterMessage.class))).thenAnswer(invocation -> invocation.getArgument(0));

        DeadLetterMessageResponse response = deadLetterService.replayDeadLetter(messageId);

        assertThat(response.status()).isEqualTo(DeadLetterStatus.REPLAYED);
        assertThat(response.replayedAt()).isNotNull();
        verify(kafkaTemplate).send("orders.created", "ORD-123", mockMessage.getPayload());
        verify(repository).save(mockMessage);
    }

    @Test
    @DisplayName("replayDeadLetter: Should throw exception if message not found")
    void replayDeadLetter_shouldThrowWhenNotFound() {
        when(repository.findById(messageId)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> deadLetterService.replayDeadLetter(messageId))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Dead letter message not found");

        verifyNoInteractions(kafkaTemplate);
    }

    @Test
    @DisplayName("discardDeadLetter: Should mark message as DISCARDED")
    void discardDeadLetter_shouldMarkDiscarded() {
        when(repository.findById(messageId)).thenReturn(Optional.of(mockMessage));
        when(repository.save(any(DeadLetterMessage.class))).thenAnswer(invocation -> invocation.getArgument(0));

        DeadLetterMessageResponse response = deadLetterService.discardDeadLetter(messageId);

        assertThat(response.status()).isEqualTo(DeadLetterStatus.DISCARDED);
        verify(repository).save(mockMessage);
    }
}
