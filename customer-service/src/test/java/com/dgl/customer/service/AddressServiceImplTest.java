package com.dgl.customer.service;

import com.dgl.customer.domain.Customer;
import com.dgl.customer.domain.CustomerAddress;
import com.dgl.customer.dto.request.CreateAddressRequest;
import com.dgl.customer.dto.response.AddressResponse;
import com.dgl.customer.exception.AddressNotFoundException;
import com.dgl.customer.exception.CustomerNotFoundException;
import com.dgl.customer.repository.CustomerAddressRepository;
import com.dgl.customer.repository.CustomerRepository;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class AddressServiceImplTest {

    @Mock
    private CustomerRepository customerRepository;

    @Mock
    private CustomerAddressRepository addressRepository;

    @InjectMocks
    private AddressServiceImpl addressService;

    @Test
    @DisplayName("addAddress should automatically mark first address as default")
    void addAddress_WhenFirstAddress_ShouldBeDefault() {
        UUID customerId = UUID.randomUUID();
        Customer customer = Customer.builder().id(customerId).build();

        CreateAddressRequest request = new CreateAddressRequest(
                "Home", "Line 1", "Line 2", "Istanbul", "Kadikoy", "34710", "Türkiye", false
        );

        when(customerRepository.findById(customerId)).thenReturn(Optional.of(customer));
        when(addressRepository.findByCustomerId(customerId)).thenReturn(List.of());

        when(addressRepository.save(any(CustomerAddress.class))).thenAnswer(invocation -> {
            CustomerAddress a = invocation.getArgument(0);
            a.setId(UUID.randomUUID());
            a.setCreatedAt(Instant.now());
            a.setUpdatedAt(Instant.now());
            return a;
        });

        AddressResponse response = addressService.addAddress(customerId, request);

        assertThat(response).isNotNull();
        assertThat(response.isDefault()).isTrue();
        assertThat(response.title()).isEqualTo("Home");
        verify(addressRepository, times(1)).save(any(CustomerAddress.class));
    }

    @Test
    @DisplayName("addAddress with isDefault=true should unmark previous default addresses")
    void addAddress_WhenNewAddressIsDefault_ShouldUnsetOldDefault() {
        UUID customerId = UUID.randomUUID();
        Customer customer = Customer.builder().id(customerId).build();

        CustomerAddress existing = CustomerAddress.builder()
                .id(UUID.randomUUID())
                .customer(customer)
                .title("Old Home")
                .isDefault(true)
                .build();

        CreateAddressRequest request = new CreateAddressRequest(
                "Office", "Line 1", null, "Ankara", "Cankaya", "06100", "Türkiye", true
        );

        when(customerRepository.findById(customerId)).thenReturn(Optional.of(customer));
        when(addressRepository.findByCustomerId(customerId)).thenReturn(new ArrayList<>(List.of(existing)));

        when(addressRepository.save(any(CustomerAddress.class))).thenAnswer(i -> {
            CustomerAddress a = i.getArgument(0);
            a.setId(UUID.randomUUID());
            return a;
        });

        AddressResponse response = addressService.addAddress(customerId, request);

        assertThat(response.isDefault()).isTrue();
        assertThat(existing.isDefault()).isFalse();
    }

    @Test
    @DisplayName("addAddress should throw CustomerNotFoundException when customer does not exist")
    void addAddress_WhenCustomerNotFound_ShouldThrowException() {
        UUID customerId = UUID.randomUUID();
        CreateAddressRequest request = new CreateAddressRequest(
                "Home", "Line 1", null, "City", "District", "12345", "Country", false
        );

        when(customerRepository.findById(customerId)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> addressService.addAddress(customerId, request))
                .isInstanceOf(CustomerNotFoundException.class);
    }

    @Test
    @DisplayName("getDefaultAddress should return default address when present")
    void getDefaultAddress_WhenExists_ShouldReturnResponse() {
        UUID customerId = UUID.randomUUID();
        Customer customer = Customer.builder().id(customerId).build();

        CustomerAddress defaultAddr = CustomerAddress.builder()
                .id(UUID.randomUUID())
                .customer(customer)
                .title("Default Home")
                .isDefault(true)
                .build();

        when(customerRepository.existsById(customerId)).thenReturn(true);
        when(addressRepository.findByCustomerId(customerId)).thenReturn(List.of(defaultAddr));

        AddressResponse response = addressService.getDefaultAddress(customerId);

        assertThat(response).isNotNull();
        assertThat(response.title()).isEqualTo("Default Home");
    }

    @Test
    @DisplayName("setDefaultAddress should change the default address successfully")
    void setDefaultAddress_WhenValid_ShouldUpdateDefaults() {
        UUID customerId = UUID.randomUUID();
        Customer customer = Customer.builder().id(customerId).build();

        UUID addr1Id = UUID.randomUUID();
        UUID addr2Id = UUID.randomUUID();

        CustomerAddress addr1 = CustomerAddress.builder()
                .id(addr1Id)
                .customer(customer)
                .isDefault(true)
                .build();

        CustomerAddress addr2 = CustomerAddress.builder()
                .id(addr2Id)
                .customer(customer)
                .isDefault(false)
                .build();

        when(customerRepository.existsById(customerId)).thenReturn(true);
        when(addressRepository.findByCustomerId(customerId)).thenReturn(List.of(addr1, addr2));

        AddressResponse response = addressService.setDefaultAddress(customerId, addr2Id);

        assertThat(response.id()).isEqualTo(addr2Id);
        assertThat(addr2.isDefault()).isTrue();
        assertThat(addr1.isDefault()).isFalse();
    }

    @Test
    @DisplayName("deleteAddress should delete address when matching customer")
    void deleteAddress_WhenValid_ShouldDelete() {
        UUID customerId = UUID.randomUUID();
        UUID addressId = UUID.randomUUID();
        Customer customer = Customer.builder().id(customerId).build();

        CustomerAddress address = CustomerAddress.builder()
                .id(addressId)
                .customer(customer)
                .build();

        when(customerRepository.existsById(customerId)).thenReturn(true);
        when(addressRepository.findById(addressId)).thenReturn(Optional.of(address));

        addressService.deleteAddress(customerId, addressId);

        verify(addressRepository, times(1)).delete(address);
    }
}
