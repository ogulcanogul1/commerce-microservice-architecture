package com.dgl.notification.cqrs.handler;

import com.dgl.notification.cqrs.QueryHandler;
import com.dgl.notification.cqrs.query.IsEventProcessedQuery;
import com.dgl.notification.domain.ProcessedEventId;
import com.dgl.notification.repository.ProcessedEventRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
@RequiredArgsConstructor
public class IsEventProcessedQueryHandler implements QueryHandler<IsEventProcessedQuery, Boolean> {

    private final ProcessedEventRepository processedEventRepository;

    @Override
    @Transactional(readOnly = true)
    public Boolean handle(IsEventProcessedQuery query) {
        ProcessedEventId id = ProcessedEventId.builder()
                .consumerGroup(query.consumerGroup())
                .eventId(query.eventId())
                .build();
        return processedEventRepository.existsById(id);
    }
}
