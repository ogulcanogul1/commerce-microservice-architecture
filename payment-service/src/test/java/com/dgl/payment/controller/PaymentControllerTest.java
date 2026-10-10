package com.dgl.payment.controller;

import com.dgl.payment.cqrs.CommandBus;
import com.dgl.payment.cqrs.QueryBus;
import com.dgl.payment.cqrs.command.ProcessPaymentCommand;
import com.dgl.payment.cqrs.command.RefundPaymentCommand;
import com.dgl.payment.cqrs.query.GetPaymentByIdQuery;
import com.dgl.payment.cqrs.query.GetPaymentByOrderIdQuery;
import com.dgl.payment.cqrs.query.GetPaymentsByCustomerQuery;
import com.dgl.payment.dto.request.ProcessPaymentRequest;
import com.dgl.payment.dto.request.RefundPaymentRequest;
import com.dgl.payment.dto.response.PaymentRefundResponse;
import com.dgl.payment.dto.response.PaymentResponse;
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
import org.springframework.data.domain.Pageable;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class PaymentControllerTest {

    @Mock
    private CommandBus commandBus;

    @Mock
    private QueryBus queryBus;

    @InjectMocks
    private PaymentController controller;

    private UUID paymentId;
    private PaymentResponse mockPaymentResponse;

    @BeforeEach
    void setUp() {
        paymentId = UUID.randomUUID();
        mockPaymentResponse = mock(PaymentResponse.class);
    }

    @Test
    @DisplayName("ProcessPayment: Should dispatch command and return 201")
    void processPayment_shouldReturn201() {
        ProcessPaymentRequest request = new ProcessPaymentRequest(UUID.randomUUID(), UUID.randomUUID(), BigDecimal.TEN, "TRY", "CREDIT_CARD");
        when(commandBus.execute(any(ProcessPaymentCommand.class))).thenReturn(mockPaymentResponse);

        ResponseEntity<PaymentResponse> response = controller.processPayment(request, "KEY-1");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        assertThat(response.getBody()).isSameAs(mockPaymentResponse);
        verify(commandBus).execute(new ProcessPaymentCommand(request, "KEY-1"));
    }

    @Test
    @DisplayName("GetPaymentById: Should dispatch query and return 200")
    void getPaymentById_shouldReturn200() {
        when(queryBus.execute(any(GetPaymentByIdQuery.class))).thenReturn(mockPaymentResponse);

        ResponseEntity<PaymentResponse> response = controller.getPaymentById(paymentId);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        verify(queryBus).execute(new GetPaymentByIdQuery(paymentId));
    }

    @Test
    @DisplayName("GetPaymentByOrderId: Should dispatch query and return 200")
    void getPaymentByOrderId_shouldReturn200() {
        UUID orderId = UUID.randomUUID();
        when(queryBus.execute(any(GetPaymentByOrderIdQuery.class))).thenReturn(mockPaymentResponse);

        ResponseEntity<PaymentResponse> response = controller.getPaymentByOrderId(orderId);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        verify(queryBus).execute(new GetPaymentByOrderIdQuery(orderId));
    }

    @Test
    @DisplayName("GetPaymentsByCustomer: Should dispatch query and return 200")
    void getPaymentsByCustomer_shouldReturn200() {
        UUID customerId = UUID.randomUUID();
        Pageable pageable = PageRequest.of(0, 10);
        Page<PaymentResponse> page = new PageImpl<>(List.of(mockPaymentResponse));
        when(queryBus.execute(any(GetPaymentsByCustomerQuery.class))).thenReturn(page);

        ResponseEntity<Page<PaymentResponse>> response = controller.getPaymentsByCustomer(customerId, pageable);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        verify(queryBus).execute(new GetPaymentsByCustomerQuery(customerId, pageable));
    }

    @Test
    @DisplayName("RefundPayment: Should dispatch command and return 200")
    void refundPayment_shouldReturn200() {
        RefundPaymentRequest request = new RefundPaymentRequest(BigDecimal.ONE, "Reason");
        PaymentRefundResponse mockRefundResponse = mock(PaymentRefundResponse.class);
        when(commandBus.execute(any(RefundPaymentCommand.class))).thenReturn(mockRefundResponse);

        ResponseEntity<PaymentRefundResponse> response = controller.refundPayment(paymentId, request);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        verify(commandBus).execute(new RefundPaymentCommand(paymentId, request));
    }
}
