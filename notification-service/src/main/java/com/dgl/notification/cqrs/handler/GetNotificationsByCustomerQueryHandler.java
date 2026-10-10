package com.dgl.notification.cqrs.handler;

import com.dgl.notification.cqrs.QueryHandler;
import com.dgl.notification.cqrs.mapper.NotificationResponseMapper;
import com.dgl.notification.cqrs.query.GetNotificationsByCustomerQuery;
import com.dgl.notification.dto.response.NotificationResponse;
import com.dgl.notification.repository.NotificationRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Component
@RequiredArgsConstructor
public class GetNotificationsByCustomerQueryHandler implements QueryHandler<GetNotificationsByCustomerQuery, List<NotificationResponse>> {

    private final NotificationRepository notificationRepository;
    private final NotificationResponseMapper responseMapper;

    @Override
    @Transactional(readOnly = true)
    public List<NotificationResponse> handle(GetNotificationsByCustomerQuery query) {
        return notificationRepository.findByCustomerIdOrderByCreatedAtDesc(query.customerId()).stream()
                .map(responseMapper::toResponse)
                .toList();
    }
}
