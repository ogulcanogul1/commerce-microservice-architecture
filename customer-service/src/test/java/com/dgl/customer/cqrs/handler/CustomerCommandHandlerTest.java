package com.dgl.customer.cqrs.handler;

import com.dgl.customer.config.CustomerMetrics;
import com.dgl.customer.cqrs.command.*;
import com.dgl.customer.cqrs.mapper.CustomerResponseMapper;
import com.dgl.customer.domain.*;
import com.dgl.customer.dto.request.*;
import com.dgl.customer.dto.response.AddressResponse;
import com.dgl.customer.dto.response.AuthResponse;
import com.dgl.customer.dto.response.CustomerResponse;
import com.dgl.customer.dto.response.PreferencesResponse;
import com.dgl.customer.exception.AddressNotFoundException;
import com.dgl.customer.exception.CustomerNotFoundException;
import com.dgl.customer.exception.EmailAlreadyExistsException;
import com.dgl.customer.exception.InvalidCredentialsException;
import com.dgl.customer.exception.InvalidTokenException;
import com.dgl.customer.outbox.OutboxService;
import com.dgl.customer.repository.CustomerAddressRepository;
import com.dgl.customer.repository.CustomerPreferencesRepository;
import com.dgl.customer.repository.CustomerRepository;
import com.dgl.customer.service.JwtService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.crypto.password.PasswordEncoder;

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
class CustomerCommandHandlerTest {

    @Mock
    private CustomerRepository customerRepository;

    @Mock
    private CustomerPreferencesRepository preferencesRepository;

    @Mock
    private CustomerAddressRepository addressRepository;

    @Mock
    private OutboxService outboxService;

    @Mock
    private CustomerMetrics customerMetrics;

    @Mock
    private PasswordEncoder passwordEncoder;

    @Mock
    private JwtService jwtService;

    private final CustomerResponseMapper responseMapper = new CustomerResponseMapper();

    private CreateCustomerCommandHandler createCustomerHandler;
    private UpdateCustomerCommandHandler updateCustomerHandler;
    private UpdatePreferencesCommandHandler updatePreferencesHandler;
    private AddAddressCommandHandler addAddressHandler;
    private SetDefaultAddressCommandHandler setDefaultAddressHandler;
    private DeleteAddressCommandHandler deleteAddressHandler;
    private RegisterCommandHandler registerHandler;
    private LoginCommandHandler loginHandler;
    private RefreshTokenCommandHandler refreshTokenHandler;
    private OAuth2LoginCommandHandler oauth2LoginHandler;

    private UUID customerId;
    private Customer sampleCustomer;

    @BeforeEach
    void setUp() {
        createCustomerHandler = new CreateCustomerCommandHandler(customerRepository, outboxService, responseMapper, customerMetrics);
        updateCustomerHandler = new UpdateCustomerCommandHandler(customerRepository, outboxService, responseMapper, customerMetrics);
        updatePreferencesHandler = new UpdatePreferencesCommandHandler(customerRepository, preferencesRepository, responseMapper);
        addAddressHandler = new AddAddressCommandHandler(customerRepository, addressRepository, responseMapper);
        setDefaultAddressHandler = new SetDefaultAddressCommandHandler(customerRepository, addressRepository, responseMapper);
        deleteAddressHandler = new DeleteAddressCommandHandler(customerRepository, addressRepository);
        registerHandler = new RegisterCommandHandler(customerRepository, passwordEncoder, jwtService, outboxService, responseMapper, customerMetrics);
        loginHandler = new LoginCommandHandler(customerRepository, passwordEncoder, jwtService, responseMapper);
        refreshTokenHandler = new RefreshTokenCommandHandler(customerRepository, jwtService, responseMapper);
        oauth2LoginHandler = new OAuth2LoginCommandHandler(customerRepository, jwtService, outboxService, responseMapper, customerMetrics);

        customerId = UUID.randomUUID();
        sampleCustomer = Customer.builder()
                .id(customerId)
                .email("test@example.com")
                .password("encoded_pass")
                .firstName("Test")
                .lastName("User")
                .phoneNumber("+905551112233")
                .status(CustomerStatus.ACTIVE)
                .role(Role.ROLE_CUSTOMER)
                .addresses(new ArrayList<>())
                .createdAt(Instant.now())
                .updatedAt(Instant.now())
                .build();
    }

    @Test
    @DisplayName("CreateCustomer: Valid request creates customer and emits outbox event")
    void createCustomer_valid_shouldCreate() {
        CreateCustomerRequest request = new CreateCustomerRequest("new@example.com", "John", "Doe", "+905551112233");
        when(customerRepository.existsByEmail("new@example.com")).thenReturn(false);
        when(customerRepository.save(any(Customer.class))).thenAnswer(i -> {
            Customer c = i.getArgument(0);
            c.setId(customerId);
            return c;
        });

        CustomerResponse response = createCustomerHandler.handle(new CreateCustomerCommand(request));

        assertThat(response).isNotNull();
        assertThat(response.email()).isEqualTo("new@example.com");
        verify(outboxService).recordEvent(eq("Customer"), anyString(), eq("CustomerCreated"), any(UUID.class), isNull(), any());
    }

    @Test
    @DisplayName("CreateCustomer: Duplicate email throws EmailAlreadyExistsException")
    void createCustomer_duplicateEmail_shouldThrow() {
        CreateCustomerRequest request = new CreateCustomerRequest("test@example.com", "John", "Doe", null);
        when(customerRepository.existsByEmail("test@example.com")).thenReturn(true);

        assertThatThrownBy(() -> createCustomerHandler.handle(new CreateCustomerCommand(request)))
                .isInstanceOf(EmailAlreadyExistsException.class);
    }

    @Test
    @DisplayName("UpdateCustomer: Valid request updates customer and emits outbox event")
    void updateCustomer_valid_shouldUpdate() {
        when(customerRepository.findById(customerId)).thenReturn(Optional.of(sampleCustomer));

        UpdateCustomerRequest request = new UpdateCustomerRequest("UpdatedFirst", "UpdatedLast", "+905559998877", CustomerStatus.SUSPENDED);
        CustomerResponse response = updateCustomerHandler.handle(new UpdateCustomerCommand(customerId, request));

        assertThat(response.firstName()).isEqualTo("UpdatedFirst");
        assertThat(sampleCustomer.getStatus()).isEqualTo(CustomerStatus.SUSPENDED);
        verify(outboxService).recordEvent(eq("Customer"), eq(customerId.toString()), eq("CustomerUpdated"), any(UUID.class), isNull(), any());
    }

    @Test
    @DisplayName("UpdatePreferences: Valid request updates preferences")
    void updatePreferences_valid_shouldUpdate() {
        when(customerRepository.findById(customerId)).thenReturn(Optional.of(sampleCustomer));
        when(preferencesRepository.save(any(CustomerPreferences.class))).thenAnswer(i -> i.getArgument(0));

        UpdatePreferencesRequest request = new UpdatePreferencesRequest(false, false, true, "en", "USD");
        PreferencesResponse response = updatePreferencesHandler.handle(new UpdatePreferencesCommand(customerId, request));

        assertThat(response).isNotNull();
        assertThat(response.emailNotifications()).isFalse();
        assertThat(response.language()).isEqualTo("en");
    }

    @Test
    @DisplayName("AddAddress: Valid address saves and returns AddressResponse")
    void addAddress_valid_shouldSave() {
        when(customerRepository.findById(customerId)).thenReturn(Optional.of(sampleCustomer));
        when(addressRepository.findByCustomerId(customerId)).thenReturn(new ArrayList<>());
        when(addressRepository.save(any(CustomerAddress.class))).thenAnswer(i -> {
            CustomerAddress a = i.getArgument(0);
            a.setId(UUID.randomUUID());
            return a;
        });

        CreateAddressRequest request = new CreateAddressRequest("Home", "Line 1", null, "Istanbul", "Kadikoy", "34000", "TR", true);
        AddressResponse response = addAddressHandler.handle(new AddAddressCommand(customerId, request));

        assertThat(response).isNotNull();
        assertThat(response.title()).isEqualTo("Home");
        assertThat(response.isDefault()).isTrue();
    }

    @Test
    @DisplayName("SetDefaultAddress: Updates default address flag")
    void setDefaultAddress_valid_shouldUpdate() {
        UUID addrId = UUID.randomUUID();
        CustomerAddress addr = CustomerAddress.builder().id(addrId).customer(sampleCustomer).isDefault(false).build();
        when(customerRepository.existsById(customerId)).thenReturn(true);
        when(addressRepository.findByCustomerId(customerId)).thenReturn(List.of(addr));

        AddressResponse response = setDefaultAddressHandler.handle(new SetDefaultAddressCommand(customerId, addrId));

        assertThat(response.isDefault()).isTrue();
    }

    @Test
    @DisplayName("DeleteAddress: Deletes existing address")
    void deleteAddress_valid_shouldDelete() {
        UUID addrId = UUID.randomUUID();
        CustomerAddress addr = CustomerAddress.builder().id(addrId).customer(sampleCustomer).build();
        when(customerRepository.existsById(customerId)).thenReturn(true);
        when(addressRepository.findById(addrId)).thenReturn(Optional.of(addr));

        deleteAddressHandler.handle(new DeleteAddressCommand(customerId, addrId));

        verify(addressRepository).delete(addr);
    }

    @Test
    @DisplayName("Register: Valid registration saves customer and returns tokens")
    void register_valid_shouldReturnTokens() {
        RegisterRequest request = new RegisterRequest("reg@example.com", "Password123!", "First", "Last", null);
        when(customerRepository.existsByEmail("reg@example.com")).thenReturn(false);
        when(passwordEncoder.encode("Password123!")).thenReturn("encoded_pass");
        when(customerRepository.save(any(Customer.class))).thenAnswer(i -> {
            Customer c = i.getArgument(0);
            c.setId(customerId);
            return c;
        });
        when(jwtService.generateAccessToken(any())).thenReturn("token_1");
        when(jwtService.generateRefreshToken(any())).thenReturn("ref_1");
        when(jwtService.getAccessTokenExpirationSeconds()).thenReturn(900L);

        AuthResponse response = registerHandler.handle(new RegisterCommand(request));

        assertThat(response.accessToken()).isEqualTo("token_1");
        assertThat(response.refreshToken()).isEqualTo("ref_1");
    }

    @Test
    @DisplayName("Login: Valid credentials returns tokens")
    void login_valid_shouldReturnTokens() {
        LoginRequest request = new LoginRequest("test@example.com", "pass");
        when(customerRepository.findByEmail("test@example.com")).thenReturn(Optional.of(sampleCustomer));
        when(passwordEncoder.matches("pass", "encoded_pass")).thenReturn(true);
        when(jwtService.generateAccessToken(sampleCustomer)).thenReturn("token_1");
        when(jwtService.generateRefreshToken(sampleCustomer)).thenReturn("ref_1");
        when(jwtService.getAccessTokenExpirationSeconds()).thenReturn(900L);

        AuthResponse response = loginHandler.handle(new LoginCommand(request));

        assertThat(response.accessToken()).isEqualTo("token_1");
    }

    @Test
    @DisplayName("Login: Invalid password throws InvalidCredentialsException")
    void login_invalidPassword_shouldThrow() {
        LoginRequest request = new LoginRequest("test@example.com", "wrong_pass");
        when(customerRepository.findByEmail("test@example.com")).thenReturn(Optional.of(sampleCustomer));
        when(passwordEncoder.matches("wrong_pass", "encoded_pass")).thenReturn(false);

        assertThatThrownBy(() -> loginHandler.handle(new LoginCommand(request)))
                .isInstanceOf(InvalidCredentialsException.class);
    }

    @Test
    @DisplayName("RefreshToken: Valid refresh token issues new tokens")
    void refreshToken_valid_shouldReturnNewTokens() {
        RefreshTokenRequest request = new RefreshTokenRequest("ref_valid");
        when(jwtService.isRefreshToken("ref_valid")).thenReturn(true);
        when(jwtService.extractCustomerId("ref_valid")).thenReturn(customerId);
        when(customerRepository.findById(customerId)).thenReturn(Optional.of(sampleCustomer));
        when(jwtService.generateAccessToken(sampleCustomer)).thenReturn("new_access");
        when(jwtService.generateRefreshToken(sampleCustomer)).thenReturn("new_ref");
        when(jwtService.getAccessTokenExpirationSeconds()).thenReturn(900L);

        AuthResponse response = refreshTokenHandler.handle(new RefreshTokenCommand(request));

        assertThat(response.accessToken()).isEqualTo("new_access");
    }
}
