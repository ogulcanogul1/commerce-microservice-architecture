package com.dgl.payment.service;

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

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class PaymentServiceImplTest {

    @Mock
    private CommandBus commandBus;

    @Mock
    private QueryBus queryBus;

    @InjectMocks
    private PaymentServiceImpl paymentService;

    @Test
    @DisplayName("processPayment: Should dispatch ProcessPaymentCommand")
    void processPayment_shouldDispatch() {
        ProcessPaymentRequest request = new ProcessPaymentRequest(UUID.randomUUID(), UUID.randomUUID(), BigDecimal.TEN, "TRY", "CREDIT_CARD");
        PaymentResponse expected = mock(PaymentResponse.class);

        when(commandBus.execute(any(ProcessPaymentCommand.class))).thenReturn(expected);

        PaymentResponse actual = paymentService.processPayment(request, "KEY-1");

        assertThat(actual).isSameAs(expected);
        verify(commandBus).execute(new ProcessPaymentCommand(request, "KEY-1"));
    }

    @Test
    @DisplayName("getPaymentById: Should dispatch GetPaymentByIdQuery")
    void getPaymentById_shouldDispatch() {
        UUID id = UUID.randomUUID();
        PaymentResponse expected = mock(PaymentResponse.class);

        when(queryBus.execute(any(GetPaymentByIdQuery.class))).thenReturn(expected);

        PaymentResponse actual = paymentService.getPaymentById(id);

        assertThat(actual).isSameAs(expected);
        verify(queryBus).execute(new GetPaymentByIdQuery(id));
    }

    @Test
    @DisplayName("getPaymentByOrderId: Should dispatch GetPaymentByOrderIdQuery")
    void getPaymentByOrderId_shouldDispatch() {
        UUID orderId = UUID.randomUUID();
        PaymentResponse expected = mock(PaymentResponse.class);

        when(queryBus.execute(any(GetPaymentByOrderIdQuery.class))).thenReturn(expected);

        PaymentResponse actual = paymentService.getPaymentByOrderId(orderId);

        assertThat(actual).isSameAs(expected);
        verify(queryBus).execute(new GetPaymentByOrderIdQuery(orderId));
    }

    @Test
    @DisplayName("getPaymentsByCustomer: Should dispatch GetPaymentsByCustomerQuery")
    void getPaymentsByCustomer_shouldDispatch() {
        UUID customerId = UUID.randomUUID();
        Pageable pageable = PageRequest.of(0, 10);
        Page<PaymentResponse> expected = new PageImpl<>(List.of());

        when(queryBus.execute(any(GetPaymentsByCustomerQuery.class))).thenReturn(expected);

        Page<PaymentResponse> actual = paymentService.getPaymentsByCustomer(customerId, pageable);

        assertThat(actual).isSameAs(expected);
        verify(queryBus).execute(new GetPaymentsByCustomerQuery(customerId, pageable));
    }

    @Test
    @DisplayName("refundPayment: Should dispatch RefundPaymentCommand")
    void refundPayment_shouldDispatch() {
        UUID id = UUID.randomUUID();
        RefundPaymentRequest request = new RefundPaymentRequest(BigDecimal.ONE, "Reason");
        PaymentRefundResponse expected = mock(PaymentRefundResponse.class);

        when(commandBus.execute(any(RefundPaymentCommand.class))).thenReturn(expected);

        PaymentRefundResponse actual = paymentService.refundPayment(id, request);

        assertThat(actual).isSameAs(expected);
        verify(commandBus).execute(new RefundPaymentCommand(id, request));
    }
}
