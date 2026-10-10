package com.dgl.payment.cqrs.handler.query;

import com.dgl.payment.cqrs.mapper.PaymentResponseMapper;
import com.dgl.payment.cqrs.query.GetPaymentByIdQuery;
import com.dgl.payment.cqrs.query.GetPaymentByOrderIdQuery;
import com.dgl.payment.cqrs.query.GetPaymentsByCustomerQuery;
import com.dgl.payment.domain.Payment;
import com.dgl.payment.domain.PaymentStatus;
import com.dgl.payment.dto.response.PaymentResponse;
import com.dgl.payment.exception.PaymentNotFoundException;
import com.dgl.payment.repository.PaymentRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class PaymentQueryHandlerTest {

    @Mock
    private PaymentRepository paymentRepository;

    private final PaymentResponseMapper mapper = new PaymentResponseMapper();

    private GetPaymentByIdQueryHandler getByIdHandler;
    private GetPaymentByOrderIdQueryHandler getByOrderIdHandler;
    private GetPaymentsByCustomerQueryHandler getByCustomerHandler;

    private UUID paymentId;
    private UUID orderId;
    private UUID customerId;
    private Payment samplePayment;

    @BeforeEach
    void setUp() {
        getByIdHandler = new GetPaymentByIdQueryHandler(paymentRepository, mapper);
        getByOrderIdHandler = new GetPaymentByOrderIdQueryHandler(paymentRepository, mapper);
        getByCustomerHandler = new GetPaymentsByCustomerQueryHandler(paymentRepository, mapper);

        paymentId = UUID.randomUUID();
        orderId = UUID.randomUUID();
        customerId = UUID.randomUUID();

        samplePayment = Payment.builder()
                .id(paymentId)
                .orderId(orderId)
                .customerId(customerId)
                .amount(new BigDecimal("100.00"))
                .currency("TRY")
                .paymentMethod("CREDIT_CARD")
                .transactionReference("TXN-12345678")
                .status(PaymentStatus.AUTHORIZED)
                .refunds(new ArrayList<>())
                .build();
    }

    @Test
    @DisplayName("GetPaymentById: Should return payment response")
    void getPaymentById_shouldSucceed() {
        when(paymentRepository.findById(paymentId)).thenReturn(Optional.of(samplePayment));

        PaymentResponse response = getByIdHandler.handle(new GetPaymentByIdQuery(paymentId));

        assertThat(response).isNotNull();
        assertThat(response.id()).isEqualTo(paymentId);
    }

    @Test
    @DisplayName("GetPaymentById: Not found should throw PaymentNotFoundException")
    void getPaymentById_notFound_shouldThrowException() {
        when(paymentRepository.findById(paymentId)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> getByIdHandler.handle(new GetPaymentByIdQuery(paymentId)))
                .isInstanceOf(PaymentNotFoundException.class);
    }

    @Test
    @DisplayName("GetPaymentByOrderId: Should return payment response")
    void getPaymentByOrderId_shouldSucceed() {
        when(paymentRepository.findByOrderId(orderId)).thenReturn(Optional.of(samplePayment));

        PaymentResponse response = getByOrderIdHandler.handle(new GetPaymentByOrderIdQuery(orderId));

        assertThat(response).isNotNull();
        assertThat(response.orderId()).isEqualTo(orderId);
    }

    @Test
    @DisplayName("GetPaymentsByCustomer: Should return paginated payments")
    void getPaymentsByCustomer_shouldSucceed() {
        Pageable pageable = PageRequest.of(0, 10);
        when(paymentRepository.findByCustomerId(customerId, pageable))
                .thenReturn(new PageImpl<>(List.of(samplePayment)));

        Page<PaymentResponse> response = getByCustomerHandler.handle(new GetPaymentsByCustomerQuery(customerId, pageable));

        assertThat(response.getContent()).hasSize(1);
    }
}
