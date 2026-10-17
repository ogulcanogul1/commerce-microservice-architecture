package com.dgl.customer.controller;

import com.dgl.customer.cqrs.CommandBus;
import com.dgl.customer.cqrs.QueryBus;
import com.dgl.customer.cqrs.command.CreateCustomerCommand;
import com.dgl.customer.cqrs.command.UpdateCustomerCommand;
import com.dgl.customer.cqrs.command.UpdatePreferencesCommand;
import com.dgl.customer.cqrs.query.GetAllCustomersQuery;
import com.dgl.customer.cqrs.query.GetCustomerByEmailQuery;
import com.dgl.customer.cqrs.query.GetCustomerByIdQuery;
import com.dgl.customer.domain.CustomerStatus;
import com.dgl.customer.dto.request.CreateCustomerRequest;
import com.dgl.customer.dto.request.UpdateCustomerRequest;
import com.dgl.customer.dto.request.UpdatePreferencesRequest;
import com.dgl.customer.dto.response.CustomerResponse;
import com.dgl.customer.dto.response.PreferencesResponse;
import com.dgl.customer.exception.AccessDeniedException;
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
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class CustomerControllerTest {

    @Mock
    private CommandBus commandBus;

    @Mock
    private QueryBus queryBus;

    @InjectMocks
    private CustomerController controller;

    private UUID customerId;
    private CustomerResponse mockCustomerResponse;
    private PreferencesResponse mockPreferencesResponse;

    @BeforeEach
    void setUp() {
        customerId = UUID.randomUUID();
        mockCustomerResponse = new CustomerResponse(
                customerId,
                "john@example.com",
                "John",
                "Doe",
                "+905551112233",
                CustomerStatus.ACTIVE,
                null,
                Instant.now(),
                Instant.now()
        );
        mockPreferencesResponse = new PreferencesResponse(
                customerId,
                true,
                true,
                true,
                "tr",
                "TRY",
                Instant.now()
        );
    }

    @Test
    @DisplayName("createCustomer: Should dispatch command and return 201 Created")
    void createCustomer_shouldReturn201() {
        CreateCustomerRequest request = new CreateCustomerRequest("john@example.com", "John", "Doe", "+905551112233");
        when(commandBus.execute(any(CreateCustomerCommand.class))).thenReturn(mockCustomerResponse);

        ResponseEntity<CustomerResponse> response = controller.createCustomer(request);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        assertThat(response.getBody()).isSameAs(mockCustomerResponse);
        verify(commandBus).execute(new CreateCustomerCommand(request));
    }

    @Test
    @DisplayName("getCustomerById: Should dispatch query and return 200 OK when owner requests")
    void getCustomerById_shouldReturn200() {
        when(queryBus.execute(any(GetCustomerByIdQuery.class))).thenReturn(mockCustomerResponse);

        ResponseEntity<CustomerResponse> response = controller.getCustomerById(
                customerId, customerId.toString(), "ROLE_CUSTOMER");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isSameAs(mockCustomerResponse);
        verify(queryBus).execute(new GetCustomerByIdQuery(customerId));
    }

    @Test
    @DisplayName("getCustomerById: Should throw AccessDeniedException when requesting another customer's profile")
    void getCustomerById_shouldThrowAccessDenied_whenCustomerMismatch() {
        String attackerUserId = UUID.randomUUID().toString();

        assertThatThrownBy(() -> controller.getCustomerById(customerId, attackerUserId, "ROLE_CUSTOMER"))
                .isInstanceOf(AccessDeniedException.class)
                .hasMessageContaining("Access denied");

        verifyNoInteractions(queryBus);
    }

    @Test
    @DisplayName("getCustomerByEmail: Should dispatch query and return 200 OK when owner requests")
    void getCustomerByEmail_shouldReturn200() {
        when(queryBus.execute(any(GetCustomerByEmailQuery.class))).thenReturn(mockCustomerResponse);

        ResponseEntity<CustomerResponse> response = controller.getCustomerByEmail(
                "john@example.com", customerId.toString(), "ROLE_CUSTOMER");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        verify(queryBus).execute(new GetCustomerByEmailQuery("john@example.com"));
    }

    @Test
    @DisplayName("getAllCustomers: Should allow admin and return 200 OK")
    void getAllCustomers_shouldAllowAdmin() {
        PageRequest pageRequest = PageRequest.of(0, 20);
        Page<CustomerResponse> page = new PageImpl<>(List.of(mockCustomerResponse));
        when(queryBus.execute(any(GetAllCustomersQuery.class))).thenReturn(page);

        ResponseEntity<Page<CustomerResponse>> response = controller.getAllCustomers(
                UUID.randomUUID().toString(), "ROLE_ADMIN", pageRequest);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        verify(queryBus).execute(new GetAllCustomersQuery(pageRequest));
    }

    @Test
    @DisplayName("getAllCustomers: Should throw AccessDeniedException when regular customer tries to list all")
    void getAllCustomers_shouldThrowAccessDenied_whenRegularCustomer() {
        PageRequest pageRequest = PageRequest.of(0, 20);

        assertThatThrownBy(() -> controller.getAllCustomers(
                customerId.toString(), "ROLE_CUSTOMER", pageRequest))
                .isInstanceOf(AccessDeniedException.class)
                .hasMessageContaining("Access denied");

        verifyNoInteractions(queryBus);
    }

    @Test
    @DisplayName("updateCustomer: Should dispatch command and return 200 OK when owner")
    void updateCustomer_shouldReturn200() {
        UpdateCustomerRequest request = new UpdateCustomerRequest("John2", "Doe2", null, null);
        when(commandBus.execute(any(UpdateCustomerCommand.class))).thenReturn(mockCustomerResponse);

        ResponseEntity<CustomerResponse> response = controller.updateCustomer(
                customerId, customerId.toString(), "ROLE_CUSTOMER", request);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        verify(commandBus).execute(new UpdateCustomerCommand(customerId, request));
    }

    @Test
    @DisplayName("updateCustomer: Should throw AccessDeniedException when updating another customer")
    void updateCustomer_shouldThrowAccessDenied_whenMismatch() {
        UpdateCustomerRequest request = new UpdateCustomerRequest("John2", "Doe2", null, null);
        String attackerUserId = UUID.randomUUID().toString();

        assertThatThrownBy(() -> controller.updateCustomer(customerId, attackerUserId, "ROLE_CUSTOMER", request))
                .isInstanceOf(AccessDeniedException.class)
                .hasMessageContaining("Access denied");

        verifyNoInteractions(commandBus);
    }

    @Test
    @DisplayName("updatePreferences: Should dispatch command and return 200 OK when owner")
    void updatePreferences_shouldReturn200() {
        UpdatePreferencesRequest request = new UpdatePreferencesRequest(false, false, true, "en", "USD");
        when(commandBus.execute(any(UpdatePreferencesCommand.class))).thenReturn(mockPreferencesResponse);

        ResponseEntity<PreferencesResponse> response = controller.updatePreferences(
                customerId, customerId.toString(), "ROLE_CUSTOMER", request);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        verify(commandBus).execute(new UpdatePreferencesCommand(customerId, request));
    }
}
