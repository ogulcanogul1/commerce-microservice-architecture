package com.dgl.customer.service;

import com.dgl.customer.cqrs.CommandBus;
import com.dgl.customer.cqrs.QueryBus;
import com.dgl.customer.cqrs.command.CreateCustomerCommand;
import com.dgl.customer.cqrs.command.UpdateCustomerCommand;
import com.dgl.customer.cqrs.command.UpdatePreferencesCommand;
import com.dgl.customer.cqrs.query.GetAllCustomersQuery;
import com.dgl.customer.cqrs.query.GetCustomerByEmailQuery;
import com.dgl.customer.cqrs.query.GetCustomerByIdQuery;
import com.dgl.customer.dto.request.CreateCustomerRequest;
import com.dgl.customer.dto.request.UpdateCustomerRequest;
import com.dgl.customer.dto.request.UpdatePreferencesRequest;
import com.dgl.customer.dto.response.CustomerResponse;
import com.dgl.customer.dto.response.PreferencesResponse;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class CustomerServiceImplTest {

    @Mock
    private CommandBus commandBus;

    @Mock
    private QueryBus queryBus;

    @InjectMocks
    private CustomerServiceImpl customerService;

    @Test
    @DisplayName("createCustomer should delegate to command bus")
    void createCustomer_shouldDelegate() {
        CreateCustomerRequest request = new CreateCustomerRequest("test@example.com", "John", "Doe", "+905551112233");
        CustomerResponse mockResponse = mock(CustomerResponse.class);
        when(commandBus.execute(any(CreateCustomerCommand.class))).thenReturn(mockResponse);

        CustomerResponse response = customerService.createCustomer(request);

        assertThat(response).isSameAs(mockResponse);
        verify(commandBus).execute(new CreateCustomerCommand(request));
    }

    @Test
    @DisplayName("updateCustomer should delegate to command bus")
    void updateCustomer_shouldDelegate() {
        UUID id = UUID.randomUUID();
        UpdateCustomerRequest request = new UpdateCustomerRequest("A", "B", null, null);
        CustomerResponse mockResponse = mock(CustomerResponse.class);
        when(commandBus.execute(any(UpdateCustomerCommand.class))).thenReturn(mockResponse);

        CustomerResponse response = customerService.updateCustomer(id, request);

        assertThat(response).isSameAs(mockResponse);
        verify(commandBus).execute(new UpdateCustomerCommand(id, request));
    }

    @Test
    @DisplayName("getCustomerById should delegate to query bus")
    void getCustomerById_shouldDelegate() {
        UUID id = UUID.randomUUID();
        CustomerResponse mockResponse = mock(CustomerResponse.class);
        when(queryBus.execute(any(GetCustomerByIdQuery.class))).thenReturn(mockResponse);

        CustomerResponse response = customerService.getCustomerById(id);

        assertThat(response).isSameAs(mockResponse);
        verify(queryBus).execute(new GetCustomerByIdQuery(id));
    }

    @Test
    @DisplayName("getCustomerByEmail should delegate to query bus")
    void getCustomerByEmail_shouldDelegate() {
        CustomerResponse mockResponse = mock(CustomerResponse.class);
        when(queryBus.execute(any(GetCustomerByEmailQuery.class))).thenReturn(mockResponse);

        CustomerResponse response = customerService.getCustomerByEmail("test@example.com");

        assertThat(response).isSameAs(mockResponse);
        verify(queryBus).execute(new GetCustomerByEmailQuery("test@example.com"));
    }

    @Test
    @DisplayName("getAllCustomers should delegate to query bus")
    void getAllCustomers_shouldDelegate() {
        PageRequest pageRequest = PageRequest.of(0, 10);
        Page<CustomerResponse> mockPage = mock(Page.class);
        when(queryBus.execute(any(GetAllCustomersQuery.class))).thenReturn(mockPage);

        Page<CustomerResponse> response = customerService.getAllCustomers(pageRequest);

        assertThat(response).isSameAs(mockPage);
        verify(queryBus).execute(new GetAllCustomersQuery(pageRequest));
    }

    @Test
    @DisplayName("updatePreferences should delegate to command bus")
    void updatePreferences_shouldDelegate() {
        UUID id = UUID.randomUUID();
        UpdatePreferencesRequest request = new UpdatePreferencesRequest(true, true, true, "tr", "TRY");
        PreferencesResponse mockResponse = mock(PreferencesResponse.class);
        when(commandBus.execute(any(UpdatePreferencesCommand.class))).thenReturn(mockResponse);

        PreferencesResponse response = customerService.updatePreferences(id, request);

        assertThat(response).isSameAs(mockResponse);
        verify(commandBus).execute(new UpdatePreferencesCommand(id, request));
    }
}
