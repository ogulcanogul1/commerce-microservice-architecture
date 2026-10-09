package com.dgl.order.service;

import com.dgl.order.domain.Order;
import com.dgl.order.domain.OrderStatus;
import com.dgl.order.repository.OrderRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.List;

/**
 * Background worker that detects orders stuck in non-terminal Saga steps
 * (e.g., PENDING, INVENTORY_RESERVED, PAYMENT_AUTHORIZED) beyond a configurable threshold,
 * cancels them, and triggers compensating Saga events across downstream microservices.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class OrderSagaTimeoutWorker {

    private final OrderRepository orderRepository;
    private final OrderService orderService;

    @Value("${saga.timeout.duration-seconds:300}")
    private long timeoutDurationSeconds;

    private static final List<OrderStatus> IN_FLIGHT_STATUSES = List.of(
            OrderStatus.PENDING,
            OrderStatus.INVENTORY_RESERVED,
            OrderStatus.PAYMENT_AUTHORIZED
    );

    @Scheduled(fixedDelayString = "${saga.timeout.check-interval-ms:30000}")
    public void processStuckSagas() {
        Instant threshold = Instant.now().minusSeconds(timeoutDurationSeconds);

        List<Order> stuckOrders = orderRepository.findByStatusInAndUpdatedAtBefore(IN_FLIGHT_STATUSES, threshold);

        if (!stuckOrders.isEmpty()) {
            log.warn("Detected {} stuck order(s) exceeding Saga timeout of {} seconds. Initiating compensation...",
                    stuckOrders.size(), timeoutDurationSeconds);

            for (Order order : stuckOrders) {
                try {
                    log.info("Timing out stuck order: id={}, orderNumber={}, currentStatus={}",
                            order.getId(), order.getOrderNumber(), order.getStatus());
                    orderService.handleSagaTimeout(order.getId());
                } catch (Exception ex) {
                    log.error("Failed to process timeout compensation for order id: {}", order.getId(), ex);
                }
            }
        }
    }
}
