package com.dgl.order.repository;

import com.dgl.order.domain.OrderSagaState;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.UUID;

@Repository
public interface OrderSagaStateRepository extends JpaRepository<OrderSagaState, UUID> {

    List<OrderSagaState> findByCurrentStep(String currentStep);

    List<OrderSagaState> findByCurrentStepInAndUpdatedAtBefore(java.util.Collection<String> currentSteps, java.time.Instant threshold);
}
