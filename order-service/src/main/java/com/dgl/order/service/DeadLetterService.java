package com.dgl.order.service;

import com.dgl.order.domain.DeadLetterStatus;
import com.dgl.order.dto.response.DeadLetterMessageResponse;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

import java.util.UUID;

public interface DeadLetterService {

    Page<DeadLetterMessageResponse> getDeadLetters(DeadLetterStatus status, Pageable pageable);

    DeadLetterMessageResponse replayDeadLetter(UUID id);

    DeadLetterMessageResponse discardDeadLetter(UUID id);
}
