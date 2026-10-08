package com.dgl.customer.service;

import com.dgl.customer.domain.Customer;
import com.dgl.customer.domain.CustomerPreferences;
import com.dgl.customer.domain.CustomerStatus;
import com.dgl.customer.dto.request.CreateCustomerRequest;
import com.dgl.customer.dto.request.UpdateCustomerRequest;
import com.dgl.customer.dto.request.UpdatePreferencesRequest;
import com.dgl.customer.dto.response.CustomerResponse;
import com.dgl.customer.dto.response.PreferencesResponse;
import com.dgl.customer.exception.CustomerNotFoundException;
import com.dgl.customer.exception.EmailAlreadyExistsException;
import com.dgl.customer.messaging.event.CustomerCreatedPayload;
import com.dgl.customer.messaging.event.CustomerUpdatedPayload;
import com.dgl.customer.outbox.OutboxService;
import com.dgl.customer.repository.CustomerPreferencesRepository;
import com.dgl.customer.repository.CustomerRepository;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class CustomerServiceImplTest {

    @Mock
    private CustomerRepository customerRepository;

    @Mock
    private CustomerPreferencesRepository preferencesRepository;

    @Mock
    private OutboxService outboxService;

    @InjectMocks
    private CustomerServiceImpl customerService;

    @Test
    @DisplayName("createCustomer should succeed, initialize preferences and record CustomerCreated outbox event")
    void createCustomer_WhenValid_ShouldSucceedAndRecordOutbox() {
        CreateCustomerRequest request = new CreateCustomerRequest(
                "john.doe@example.com",
                "John",
                "Doe",
                "+905551112233"
        );

        when(customerRepository.existsByEmail("john.doe@example.com")).thenReturn(false);
        when(customerRepository.save(any(Customer.class))).thenAnswer(invocation -> {
            Customer c = invocation.getArgument(0);
            c.setId(UUID.randomUUID());
            c.setCreatedAt(Instant.now());
            c.setUpdatedAt(Instant.now());
            return c;
        });

        CustomerResponse response = customerService.createCustomer(request);

        assertThat(response).isNotNull();
        assertThat(response.email()).isEqualTo("john.doe@example.com");
        assertThat(response.firstName()).isEqualTo("John");
        assertThat(response.status()).isEqualTo(CustomerStatus.ACTIVE);
        assertThat(response.preferences()).isNotNull();
        assertThat(response.preferences().emailNotifications()).isTrue();

        verify(outboxService, times(1)).recordEvent(
                eq("Customer"),
                anyString(),
                eq("CustomerCreated"),
                any(UUID.class),
                isNull(),
                any(CustomerCreatedPayload.class)
        );
    }

    @Test
    @DisplayName("createCustomer should throw EmailAlreadyExistsException when email is taken")
    void createCustomer_WhenEmailExists_ShouldThrowException() {
        CreateCustomerRequest request = new CreateCustomerRequest(
                "existing@example.com",
                "Jane",
                "Doe",
                null
        );

        when(customerRepository.existsByEmail("existing@example.com")).thenReturn(true);

        assertThatThrownBy(() -> customerService.createCustomer(request))
                .isInstanceOf(EmailAlreadyExistsException.class)
                .hasMessageContaining("existing@example.com");

        verify(customerRepository, never()).save(any(Customer.class));
        verifyNoInteractions(outboxService);
    }

    @Test
    @DisplayName("updateCustomer should update details and record CustomerUpdated outbox event")
    void updateCustomer_WhenValid_ShouldSucceed() {
        UUID customerId = UUID.randomUUID();
        Customer customer = Customer.builder()
                .id(customerId)
                .email("test@example.com")
                .firstName("Old")
                .lastName("Name")
                .phoneNumber("+905550000000")
                .status(CustomerStatus.ACTIVE)
                .build();

        UpdateCustomerRequest updateRequest = new UpdateCustomerRequest(
                "UpdatedFirst",
                "UpdatedLast",
                "+905559998877",
                CustomerStatus.SUSPENDED
        );

        when(customerRepository.findById(customerId)).thenReturn(Optional.of(customer));

        CustomerResponse response = customerService.updateCustomer(customerId, updateRequest);

        assertThat(response).isNotNull();
        assertThat(customer.getFirstName()).isEqualTo("UpdatedFirst");
        assertThat(customer.getLastName()).isEqualTo("UpdatedLast");
        assertThat(customer.getPhoneNumber()).isEqualTo("+905559998877");
        assertThat(customer.getStatus()).isEqualTo(CustomerStatus.SUSPENDED);

        verify(outboxService, times(1)).recordEvent(
                eq("Customer"),
                eq(customerId.toString()),
                eq("CustomerUpdated"),
                any(UUID.class),
                isNull(),
                any(CustomerUpdatedPayload.class)
        );
    }

    @Test
    @DisplayName("updateCustomer should throw CustomerNotFoundException when customer does not exist")
    void updateCustomer_WhenNotFound_ShouldThrowException() {
        UUID customerId = UUID.randomUUID();
        UpdateCustomerRequest updateRequest = new UpdateCustomerRequest("A", "B", null, CustomerStatus.ACTIVE);

        when(customerRepository.findById(customerId)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> customerService.updateCustomer(customerId, updateRequest))
                .isInstanceOf(CustomerNotFoundException.class);
    }

    @Test
    @DisplayName("getCustomerById should return customer response when exists")
    void getCustomerById_WhenExists_ShouldReturnResponse() {
        UUID customerId = UUID.randomUUID();
        Customer customer = Customer.builder()
                .id(customerId)
                .email("test@example.com")
                .firstName("Test")
                .lastName("User")
                .status(CustomerStatus.ACTIVE)
                .build();

        when(customerRepository.findById(customerId)).thenReturn(Optional.of(customer));

        CustomerResponse response = customerService.getCustomerById(customerId);

        assertThat(response).isNotNull();
        assertThat(response.id()).isEqualTo(customerId);
    }

    @Test
    @DisplayName("getCustomerByEmail should return customer response when email exists")
    void getCustomerByEmail_WhenExists_ShouldReturnResponse() {
        Customer customer = Customer.builder()
                .id(UUID.randomUUID())
                .email("test@example.com")
                .firstName("Test")
                .lastName("User")
                .status(CustomerStatus.ACTIVE)
                .build();

        when(customerRepository.findByEmail("test@example.com")).thenReturn(Optional.of(customer));

        CustomerResponse response = customerService.getCustomerByEmail("test@example.com");

        assertThat(response).isNotNull();
        assertThat(response.email()).isEqualTo("test@example.com");
    }

    @Test
    @DisplayName("updatePreferences should update preference flags and return PreferencesResponse")
    void updatePreferences_WhenValid_ShouldUpdateAndReturnResponse() {
        UUID customerId = UUID.randomUUID();
        CustomerPreferences prefs = CustomerPreferences.builder()
                .customerId(customerId)
                .emailNotifications(true)
                .smsNotifications(true)
                .pushNotifications(true)
                .language("tr")
                .currency("TRY")
                .build();

        Customer customer = Customer.builder()
                .id(customerId)
                .email("test@example.com")
                .preferences(prefs)
                .build();

        UpdatePreferencesRequest request = new UpdatePreferencesRequest(
                false,
                false,
                true,
                "en",
                "USD"
        );

        when(customerRepository.findById(customerId)).thenReturn(Optional.of(customer));
        when(preferencesRepository.save(any(CustomerPreferences.class))).thenAnswer(i -> i.getArgument(0));

        PreferencesResponse response = customerService.updatePreferences(customerId, request);

        assertThat(response).isNotNull();
        assertThat(response.emailNotifications()).isFalse();
        assertThat(response.smsNotifications()).isFalse();
        assertThat(response.pushNotifications()).isTrue();
        assertThat(response.language()).isEqualTo("en");
        assertThat(response.currency()).isEqualTo("USD");
    }
}
