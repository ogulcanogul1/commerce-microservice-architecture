package com.dgl.notification.cqrs.handler;

import com.dgl.notification.cqrs.CommandHandler;
import com.dgl.notification.cqrs.command.MarkEventProcessedCommand;
import com.dgl.notification.domain.ProcessedEvent;
import com.dgl.notification.domain.ProcessedEventId;
import com.dgl.notification.repository.ProcessedEventRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
@RequiredArgsConstructor
public class MarkEventProcessedCommandHandler implements CommandHandler<MarkEventProcessedCommand, Void> {

    private final ProcessedEventRepository processedEventRepository;

    @Override
    @Transactional
    public Void handle(MarkEventProcessedCommand command) {
        ProcessedEventId id = ProcessedEventId.builder()
                .consumerGroup(command.consumerGroup())
                .eventId(command.eventId())
                .build();

        ProcessedEvent event = ProcessedEvent.builder()
                .id(id)
                .eventType(command.eventType())
                .build();

        processedEventRepository.save(event);
        return null;
    }
}
