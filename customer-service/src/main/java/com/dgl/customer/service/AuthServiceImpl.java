package com.dgl.customer.service;

import com.dgl.customer.config.CustomerMetrics;
import com.dgl.customer.domain.*;
import com.dgl.customer.dto.request.LoginRequest;
import com.dgl.customer.dto.request.OAuth2LoginRequest;
import com.dgl.customer.dto.request.RefreshTokenRequest;
import com.dgl.customer.dto.request.RegisterRequest;
import com.dgl.customer.dto.response.AuthResponse;
import com.dgl.customer.dto.response.CustomerResponse;
import com.dgl.customer.dto.response.PreferencesResponse;
import com.dgl.customer.exception.EmailAlreadyExistsException;
import com.dgl.customer.exception.InvalidCredentialsException;
import com.dgl.customer.exception.InvalidTokenException;
import com.dgl.customer.messaging.event.CustomerCreatedPayload;
import com.dgl.customer.outbox.OutboxService;
import com.dgl.customer.repository.CustomerRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class AuthServiceImpl implements AuthService {

    private final CustomerRepository customerRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtService jwtService;
    private final OutboxService outboxService;
    private final CustomerMetrics customerMetrics;

    @Override
    @Transactional
    public AuthResponse register(RegisterRequest request) {
        String normalizedEmail = request.email().toLowerCase().trim();
        log.info("Processing registration for email: {}", normalizedEmail);

        if (customerRepository.existsByEmail(normalizedEmail)) {
            throw new EmailAlreadyExistsException("Customer with email '" + normalizedEmail + "' already exists");
        }

        Customer customer = Customer.builder()
                .email(normalizedEmail)
                .password(passwordEncoder.encode(request.password()))
                .firstName(request.firstName().trim())
                .lastName(request.lastName().trim())
                .phoneNumber(request.phoneNumber())
                .role(Role.ROLE_CUSTOMER)
                .authProvider(AuthProvider.LOCAL)
                .status(CustomerStatus.ACTIVE)
                .addresses(new ArrayList<>())
                .build();

        CustomerPreferences preferences = CustomerPreferences.builder()
                .customer(customer)
                .emailNotifications(true)
                .smsNotifications(true)
                .pushNotifications(true)
                .language("tr")
                .currency("TRY")
                .build();

        customer.setPreferences(preferences);

        Customer saved = customerRepository.save(customer);

        outboxService.recordEvent(
                "Customer",
                saved.getId().toString(),
                "CustomerCreated",
                UUID.randomUUID(),
                null,
                new CustomerCreatedPayload(
                        saved.getId(),
                        saved.getEmail(),
                        saved.getFirstName(),
                        saved.getLastName(),
                        saved.getPhoneNumber(),
                        saved.getStatus().name()
                )
        );

        if (customerMetrics != null) {
            customerMetrics.incrementCreated();
        }

        String accessToken = jwtService.generateAccessToken(saved);
        String refreshToken = jwtService.generateRefreshToken(saved);

        return AuthResponse.of(accessToken, refreshToken, jwtService.getAccessTokenExpirationSeconds(), mapToResponse(saved));
    }

    @Override
    @Transactional(readOnly = true)
    public AuthResponse login(LoginRequest request) {
        String normalizedEmail = request.email().toLowerCase().trim();
        log.info("Processing login attempt for email: {}", normalizedEmail);

        Customer customer = customerRepository.findByEmail(normalizedEmail)
                .orElseThrow(InvalidCredentialsException::new);

        if (customer.getPassword() == null || !passwordEncoder.matches(request.password(), customer.getPassword())) {
            log.warn("Invalid credentials for email: {}", normalizedEmail);
            throw new InvalidCredentialsException();
        }

        if (customer.getStatus() != CustomerStatus.ACTIVE) {
            log.warn("Account is not active for email: {}, status: {}", normalizedEmail, customer.getStatus());
            throw new InvalidCredentialsException("Account is not active");
        }

        String accessToken = jwtService.generateAccessToken(customer);
        String refreshToken = jwtService.generateRefreshToken(customer);

        return AuthResponse.of(accessToken, refreshToken, jwtService.getAccessTokenExpirationSeconds(), mapToResponse(customer));
    }

    @Override
    @Transactional(readOnly = true)
    public AuthResponse refreshToken(RefreshTokenRequest request) {
        if (!jwtService.isRefreshToken(request.refreshToken())) {
            throw new InvalidTokenException("Supplied token is not a valid refresh token");
        }

        UUID customerId = jwtService.extractCustomerId(request.refreshToken());
        Customer customer = customerRepository.findById(customerId)
                .orElseThrow(() -> new InvalidTokenException("Customer associated with token does not exist"));

        if (customer.getStatus() != CustomerStatus.ACTIVE) {
            throw new InvalidTokenException("Customer account is not active");
        }

        String newAccessToken = jwtService.generateAccessToken(customer);
        String newRefreshToken = jwtService.generateRefreshToken(customer);

        return AuthResponse.of(newAccessToken, newRefreshToken, jwtService.getAccessTokenExpirationSeconds(), mapToResponse(customer));
    }

    @Override
    @Transactional
    public AuthResponse oauth2Login(OAuth2LoginRequest request) {
        String normalizedEmail = request.email().toLowerCase().trim();
        log.info("Processing OAuth2 login for provider: {}, email: {}", request.provider(), normalizedEmail);

        Customer customer = customerRepository.findByAuthProviderAndProviderId(request.provider(), request.providerId())
                .or(() -> customerRepository.findByEmail(normalizedEmail))
                .orElseGet(() -> {
                    log.info("Creating new customer from OAuth2 profile: {}", normalizedEmail);
                    Customer newCustomer = Customer.builder()
                            .email(normalizedEmail)
                            .firstName(request.firstName().trim())
                            .lastName(request.lastName().trim())
                            .authProvider(request.provider())
                            .providerId(request.providerId())
                            .role(Role.ROLE_CUSTOMER)
                            .status(CustomerStatus.ACTIVE)
                            .addresses(new ArrayList<>())
                            .build();

                    CustomerPreferences prefs = CustomerPreferences.builder()
                            .customer(newCustomer)
                            .emailNotifications(true)
                            .smsNotifications(true)
                            .pushNotifications(true)
                            .language("tr")
                            .currency("TRY")
                            .build();

                    newCustomer.setPreferences(prefs);
                    Customer saved = customerRepository.save(newCustomer);

                    outboxService.recordEvent(
                            "Customer",
                            saved.getId().toString(),
                            "CustomerCreated",
                            UUID.randomUUID(),
                            null,
                            new CustomerCreatedPayload(
                                    saved.getId(),
                                    saved.getEmail(),
                                    saved.getFirstName(),
                                    saved.getLastName(),
                                    saved.getPhoneNumber(),
                                    saved.getStatus().name()
                            )
                    );

                    if (customerMetrics != null) {
                        customerMetrics.incrementCreated();
                    }

                    return saved;
                });

        if (customer.getProviderId() == null) {
            customer.setAuthProvider(request.provider());
            customer.setProviderId(request.providerId());
            customer = customerRepository.save(customer);
        }

        String accessToken = jwtService.generateAccessToken(customer);
        String refreshToken = jwtService.generateRefreshToken(customer);

        return AuthResponse.of(accessToken, refreshToken, jwtService.getAccessTokenExpirationSeconds(), mapToResponse(customer));
    }

    private CustomerResponse mapToResponse(Customer customer) {
        PreferencesResponse prefsResponse = customer.getPreferences() != null
                ? new PreferencesResponse(
                        customer.getPreferences().getCustomerId(),
                        customer.getPreferences().isEmailNotifications(),
                        customer.getPreferences().isSmsNotifications(),
                        customer.getPreferences().isPushNotifications(),
                        customer.getPreferences().getLanguage(),
                        customer.getPreferences().getCurrency(),
                        customer.getPreferences().getUpdatedAt()
                )
                : null;

        return new CustomerResponse(
                customer.getId(),
                customer.getEmail(),
                customer.getFirstName(),
                customer.getLastName(),
                customer.getPhoneNumber(),
                customer.getStatus(),
                prefsResponse,
                customer.getCreatedAt(),
                customer.getUpdatedAt()
        );
    }
}
