package com.dgl.customer.service;

import com.dgl.customer.config.CustomerMetrics;
import com.dgl.customer.domain.AuthProvider;
import com.dgl.customer.domain.Customer;
import com.dgl.customer.domain.CustomerStatus;
import com.dgl.customer.domain.Role;
import com.dgl.customer.dto.request.LoginRequest;
import com.dgl.customer.dto.request.OAuth2LoginRequest;
import com.dgl.customer.dto.request.RefreshTokenRequest;
import com.dgl.customer.dto.request.RegisterRequest;
import com.dgl.customer.dto.response.AuthResponse;
import com.dgl.customer.exception.EmailAlreadyExistsException;
import com.dgl.customer.exception.InvalidCredentialsException;
import com.dgl.customer.exception.InvalidTokenException;
import com.dgl.customer.outbox.OutboxService;
import com.dgl.customer.repository.CustomerRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.crypto.password.PasswordEncoder;

import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class AuthServiceImplTest {

    @Mock
    private CustomerRepository customerRepository;

    @Mock
    private PasswordEncoder passwordEncoder;

    @Mock
    private JwtService jwtService;

    @Mock
    private OutboxService outboxService;

    @Mock
    private CustomerMetrics customerMetrics;

    private AuthServiceImpl authService;

    private Customer sampleCustomer;
    private final UUID customerId = UUID.randomUUID();

    @BeforeEach
    void setUp() {
        authService = new AuthServiceImpl(
                customerRepository,
                passwordEncoder,
                jwtService,
                outboxService,
                customerMetrics
        );

        sampleCustomer = Customer.builder()
                .id(customerId)
                .email("john.doe@example.com")
                .password("encoded_password")
                .firstName("John")
                .lastName("Doe")
                .phoneNumber("+905551234567")
                .role(Role.ROLE_CUSTOMER)
                .authProvider(AuthProvider.LOCAL)
                .status(CustomerStatus.ACTIVE)
                .build();
    }

    @Test
    @DisplayName("register: when email does not exist, should create customer and return auth response")
    void register_WhenValidRequest_ShouldCreateCustomerAndReturnTokens() {
        RegisterRequest request = new RegisterRequest("john.doe@example.com", "Password123!", "John", "Doe", "+905551234567");

        when(customerRepository.existsByEmail("john.doe@example.com")).thenReturn(false);
        when(passwordEncoder.encode("Password123!")).thenReturn("encoded_password");
        when(customerRepository.save(any(Customer.class))).thenReturn(sampleCustomer);
        when(jwtService.generateAccessToken(sampleCustomer)).thenReturn("access_token");
        when(jwtService.generateRefreshToken(sampleCustomer)).thenReturn("refresh_token");
        when(jwtService.getAccessTokenExpirationSeconds()).thenReturn(900L);

        AuthResponse response = authService.register(request);

        assertThat(response).isNotNull();
        assertThat(response.accessToken()).isEqualTo("access_token");
        assertThat(response.refreshToken()).isEqualTo("refresh_token");
        assertThat(response.tokenType()).isEqualTo("Bearer");
        assertThat(response.expiresIn()).isEqualTo(900L);
        assertThat(response.customer().email()).isEqualTo("john.doe@example.com");

        verify(customerRepository).save(any(Customer.class));
        verify(outboxService).recordEvent(eq("Customer"), eq(customerId.toString()), eq("CustomerCreated"), any(), any(), any());
    }

    @Test
    @DisplayName("register: when email already exists, should throw EmailAlreadyExistsException")
    void register_WhenEmailAlreadyExists_ShouldThrowException() {
        RegisterRequest request = new RegisterRequest("john.doe@example.com", "Password123!", "John", "Doe", null);

        when(customerRepository.existsByEmail("john.doe@example.com")).thenReturn(true);

        assertThatThrownBy(() -> authService.register(request))
                .isInstanceOf(EmailAlreadyExistsException.class)
                .hasMessageContaining("john.doe@example.com");

        verify(customerRepository, never()).save(any());
    }

    @Test
    @DisplayName("login: when credentials are valid, should return auth response")
    void login_WhenValidCredentials_ShouldReturnTokens() {
        LoginRequest request = new LoginRequest("john.doe@example.com", "Password123!");

        when(customerRepository.findByEmail("john.doe@example.com")).thenReturn(Optional.of(sampleCustomer));
        when(passwordEncoder.matches("Password123!", "encoded_password")).thenReturn(true);
        when(jwtService.generateAccessToken(sampleCustomer)).thenReturn("access_token");
        when(jwtService.generateRefreshToken(sampleCustomer)).thenReturn("refresh_token");
        when(jwtService.getAccessTokenExpirationSeconds()).thenReturn(900L);

        AuthResponse response = authService.login(request);

        assertThat(response).isNotNull();
        assertThat(response.accessToken()).isEqualTo("access_token");
        assertThat(response.refreshToken()).isEqualTo("refresh_token");
    }

    @Test
    @DisplayName("login: when customer does not exist, should throw InvalidCredentialsException")
    void login_WhenCustomerNotFound_ShouldThrowInvalidCredentialsException() {
        LoginRequest request = new LoginRequest("unknown@example.com", "password");

        when(customerRepository.findByEmail("unknown@example.com")).thenReturn(Optional.empty());

        assertThatThrownBy(() -> authService.login(request))
                .isInstanceOf(InvalidCredentialsException.class);
    }

    @Test
    @DisplayName("login: when password does not match, should throw InvalidCredentialsException")
    void login_WhenPasswordMismatch_ShouldThrowInvalidCredentialsException() {
        LoginRequest request = new LoginRequest("john.doe@example.com", "wrong_password");

        when(customerRepository.findByEmail("john.doe@example.com")).thenReturn(Optional.of(sampleCustomer));
        when(passwordEncoder.matches("wrong_password", "encoded_password")).thenReturn(false);

        assertThatThrownBy(() -> authService.login(request))
                .isInstanceOf(InvalidCredentialsException.class);
    }

    @Test
    @DisplayName("login: when account is suspended, should throw InvalidCredentialsException")
    void login_WhenAccountSuspended_ShouldThrowInvalidCredentialsException() {
        sampleCustomer.setStatus(CustomerStatus.SUSPENDED);
        LoginRequest request = new LoginRequest("john.doe@example.com", "Password123!");

        when(customerRepository.findByEmail("john.doe@example.com")).thenReturn(Optional.of(sampleCustomer));
        when(passwordEncoder.matches("Password123!", "encoded_password")).thenReturn(true);

        assertThatThrownBy(() -> authService.login(request))
                .isInstanceOf(InvalidCredentialsException.class)
                .hasMessageContaining("Account is not active");
    }

    @Test
    @DisplayName("refreshToken: when token is valid refresh token, should return new tokens")
    void refreshToken_WhenValidToken_ShouldReturnNewTokens() {
        RefreshTokenRequest request = new RefreshTokenRequest("valid_refresh_token");

        when(jwtService.isRefreshToken("valid_refresh_token")).thenReturn(true);
        when(jwtService.extractCustomerId("valid_refresh_token")).thenReturn(customerId);
        when(customerRepository.findById(customerId)).thenReturn(Optional.of(sampleCustomer));
        when(jwtService.generateAccessToken(sampleCustomer)).thenReturn("new_access_token");
        when(jwtService.generateRefreshToken(sampleCustomer)).thenReturn("new_refresh_token");
        when(jwtService.getAccessTokenExpirationSeconds()).thenReturn(900L);

        AuthResponse response = authService.refreshToken(request);

        assertThat(response).isNotNull();
        assertThat(response.accessToken()).isEqualTo("new_access_token");
        assertThat(response.refreshToken()).isEqualTo("new_refresh_token");
    }

    @Test
    @DisplayName("refreshToken: when token is not a refresh token, should throw InvalidTokenException")
    void refreshToken_WhenNotRefreshToken_ShouldThrowInvalidTokenException() {
        RefreshTokenRequest request = new RefreshTokenRequest("access_token_sent_as_refresh");

        when(jwtService.isRefreshToken("access_token_sent_as_refresh")).thenReturn(false);

        assertThatThrownBy(() -> authService.refreshToken(request))
                .isInstanceOf(InvalidTokenException.class);
    }

    @Test
    @DisplayName("oauth2Login: when customer already exists, should return auth response")
    void oauth2Login_WhenExistingCustomer_ShouldReturnTokens() {
        OAuth2LoginRequest request = new OAuth2LoginRequest(AuthProvider.GOOGLE, "google_123", "john.doe@example.com", "John", "Doe");
        sampleCustomer.setAuthProvider(AuthProvider.GOOGLE);
        sampleCustomer.setProviderId("google_123");

        when(customerRepository.findByAuthProviderAndProviderId(AuthProvider.GOOGLE, "google_123"))
                .thenReturn(Optional.of(sampleCustomer));
        when(jwtService.generateAccessToken(sampleCustomer)).thenReturn("access_token");
        when(jwtService.generateRefreshToken(sampleCustomer)).thenReturn("refresh_token");
        when(jwtService.getAccessTokenExpirationSeconds()).thenReturn(900L);

        AuthResponse response = authService.oauth2Login(request);

        assertThat(response).isNotNull();
        assertThat(response.accessToken()).isEqualTo("access_token");
    }

    @Test
    @DisplayName("oauth2Login: when customer does not exist, should create customer and return tokens")
    void oauth2Login_WhenNewCustomer_ShouldCreateAndReturnTokens() {
        OAuth2LoginRequest request = new OAuth2LoginRequest(AuthProvider.GOOGLE, "google_999", "new.user@example.com", "New", "User");

        when(customerRepository.findByAuthProviderAndProviderId(AuthProvider.GOOGLE, "google_999")).thenReturn(Optional.empty());
        when(customerRepository.findByEmail("new.user@example.com")).thenReturn(Optional.empty());
        when(customerRepository.save(any(Customer.class))).thenAnswer(invocation -> {
            Customer c = invocation.getArgument(0);
            c.setId(UUID.randomUUID());
            return c;
        });
        when(jwtService.generateAccessToken(any())).thenReturn("new_oauth_access_token");
        when(jwtService.generateRefreshToken(any())).thenReturn("new_oauth_refresh_token");
        when(jwtService.getAccessTokenExpirationSeconds()).thenReturn(900L);

        AuthResponse response = authService.oauth2Login(request);

        assertThat(response).isNotNull();
        assertThat(response.accessToken()).isEqualTo("new_oauth_access_token");
        verify(customerRepository).save(any(Customer.class));
        verify(outboxService).recordEvent(eq("Customer"), any(), eq("CustomerCreated"), any(), any(), any());
    }
}
