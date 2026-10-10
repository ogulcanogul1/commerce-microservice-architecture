package com.dgl.customer.cqrs.handler;

import com.dgl.customer.cqrs.mapper.CustomerResponseMapper;
import com.dgl.customer.cqrs.query.*;
import com.dgl.customer.domain.Customer;
import com.dgl.customer.domain.CustomerAddress;
import com.dgl.customer.domain.CustomerStatus;
import com.dgl.customer.dto.response.AddressResponse;
import com.dgl.customer.dto.response.CustomerResponse;
import com.dgl.customer.exception.AddressNotFoundException;
import com.dgl.customer.exception.CustomerNotFoundException;
import com.dgl.customer.repository.CustomerAddressRepository;
import com.dgl.customer.repository.CustomerRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class CustomerQueryHandlerTest {

    @Mock
    private CustomerRepository customerRepository;

    @Mock
    private CustomerAddressRepository addressRepository;

    private final CustomerResponseMapper responseMapper = new CustomerResponseMapper();

    private GetCustomerByIdQueryHandler getByIdHandler;
    private GetCustomerByEmailQueryHandler getByEmailHandler;
    private GetAllCustomersQueryHandler getAllHandler;
    private GetCustomerAddressesQueryHandler getAddressesHandler;
    private GetDefaultAddressQueryHandler getDefaultAddressHandler;

    private UUID customerId;
    private Customer sampleCustomer;

    @BeforeEach
    void setUp() {
        getByIdHandler = new GetCustomerByIdQueryHandler(customerRepository, responseMapper);
        getByEmailHandler = new GetCustomerByEmailQueryHandler(customerRepository, responseMapper);
        getAllHandler = new GetAllCustomersQueryHandler(customerRepository, responseMapper);
        getAddressesHandler = new GetCustomerAddressesQueryHandler(customerRepository, addressRepository, responseMapper);
        getDefaultAddressHandler = new GetDefaultAddressQueryHandler(customerRepository, addressRepository, responseMapper);

        customerId = UUID.randomUUID();
        sampleCustomer = Customer.builder()
                .id(customerId)
                .email("test@example.com")
                .firstName("Test")
                .lastName("User")
                .status(CustomerStatus.ACTIVE)
                .build();
    }

    @Test
    @DisplayName("getCustomerById: Found customer returns response")
    void getCustomerById_found_shouldReturn() {
        when(customerRepository.findById(customerId)).thenReturn(Optional.of(sampleCustomer));

        CustomerResponse response = getByIdHandler.handle(new GetCustomerByIdQuery(customerId));

        assertThat(response.id()).isEqualTo(customerId);
    }

    @Test
    @DisplayName("getCustomerById: Not found customer throws CustomerNotFoundException")
    void getCustomerById_notFound_shouldThrow() {
        when(customerRepository.findById(customerId)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> getByIdHandler.handle(new GetCustomerByIdQuery(customerId)))
                .isInstanceOf(CustomerNotFoundException.class);
    }

    @Test
    @DisplayName("getCustomerByEmail: Found customer returns response")
    void getCustomerByEmail_found_shouldReturn() {
        when(customerRepository.findByEmail("test@example.com")).thenReturn(Optional.of(sampleCustomer));

        CustomerResponse response = getByEmailHandler.handle(new GetCustomerByEmailQuery("test@example.com"));

        assertThat(response.email()).isEqualTo("test@example.com");
    }

    @Test
    @DisplayName("getAllCustomers: Returns paginated customers")
    void getAllCustomers_shouldReturnPage() {
        PageRequest pageRequest = PageRequest.of(0, 10);
        when(customerRepository.findAll(pageRequest)).thenReturn(new PageImpl<>(List.of(sampleCustomer)));

        Page<CustomerResponse> page = getAllHandler.handle(new GetAllCustomersQuery(pageRequest));

        assertThat(page.getTotalElements()).isEqualTo(1);
    }

    @Test
    @DisplayName("getCustomerAddresses: Returns list of customer addresses")
    void getCustomerAddresses_shouldReturnList() {
        CustomerAddress address = CustomerAddress.builder().id(UUID.randomUUID()).customer(sampleCustomer).title("Home").build();
        when(customerRepository.existsById(customerId)).thenReturn(true);
        when(addressRepository.findByCustomerId(customerId)).thenReturn(List.of(address));

        List<AddressResponse> list = getAddressesHandler.handle(new GetCustomerAddressesQuery(customerId));

        assertThat(list).hasSize(1);
    }

    @Test
    @DisplayName("getDefaultAddress: Found default address returns AddressResponse")
    void getDefaultAddress_found_shouldReturn() {
        CustomerAddress address = CustomerAddress.builder().id(UUID.randomUUID()).customer(sampleCustomer).title("Home").isDefault(true).build();
        when(customerRepository.existsById(customerId)).thenReturn(true);
        when(addressRepository.findByCustomerId(customerId)).thenReturn(List.of(address));

        AddressResponse response = getDefaultAddressHandler.handle(new GetDefaultAddressQuery(customerId));

        assertThat(response.isDefault()).isTrue();
    }

    @Test
    @DisplayName("getDefaultAddress: No default address throws AddressNotFoundException")
    void getDefaultAddress_notFound_shouldThrow() {
        when(customerRepository.existsById(customerId)).thenReturn(true);
        when(addressRepository.findByCustomerId(customerId)).thenReturn(List.of());

        assertThatThrownBy(() -> getDefaultAddressHandler.handle(new GetDefaultAddressQuery(customerId)))
                .isInstanceOf(AddressNotFoundException.class);
    }
}
