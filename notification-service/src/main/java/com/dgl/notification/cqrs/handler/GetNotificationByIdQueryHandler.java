package com.dgl.notification.cqrs.handler;

import com.dgl.notification.cqrs.QueryHandler;
import com.dgl.notification.cqrs.mapper.NotificationResponseMapper;
import com.dgl.notification.cqrs.query.GetNotificationByIdQuery;
import com.dgl.notification.domain.Notification;
import com.dgl.notification.dto.response.NotificationResponse;
import com.dgl.notification.exception.NotificationNotFoundException;
import com.dgl.notification.repository.NotificationRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
@RequiredArgsConstructor
public class GetNotificationByIdQueryHandler implements QueryHandler<GetNotificationByIdQuery, NotificationResponse> {

    private final NotificationRepository notificationRepository;
    private final NotificationResponseMapper responseMapper;

    @Override
    @Transactional(readOnly = true)
    public NotificationResponse handle(GetNotificationByIdQuery query) {
        Notification notification = notificationRepository.findById(query.id())
                .orElseThrow(() -> new NotificationNotFoundException(query.id()));
        return responseMapper.toResponse(notification);
    }
}
