package com.dgl.customer.cqrs.handler;

import com.dgl.customer.config.CustomerMetrics;
import com.dgl.customer.cqrs.CommandHandler;
import com.dgl.customer.cqrs.command.RegisterCommand;
import com.dgl.customer.cqrs.mapper.CustomerResponseMapper;
import com.dgl.customer.domain.AuthProvider;
import com.dgl.customer.domain.Customer;
import com.dgl.customer.domain.CustomerPreferences;
import com.dgl.customer.domain.CustomerStatus;
import com.dgl.customer.domain.Role;
import com.dgl.customer.dto.request.RegisterRequest;
import com.dgl.customer.dto.response.AuthResponse;
import com.dgl.customer.exception.EmailAlreadyExistsException;
import com.dgl.customer.messaging.event.CustomerCreatedPayload;
import com.dgl.customer.outbox.OutboxService;
import com.dgl.customer.repository.CustomerRepository;
import com.dgl.customer.service.JwtService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.UUID;

@Slf4j
@Component
public class RegisterCommandHandler implements CommandHandler<RegisterCommand, AuthResponse> {

    private final CustomerRepository customerRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtService jwtService;
    private final OutboxService outboxService;
    private final CustomerResponseMapper responseMapper;
    private final CustomerMetrics customerMetrics;

    public RegisterCommandHandler(
            CustomerRepository customerRepository,
            PasswordEncoder passwordEncoder,
            JwtService jwtService,
            OutboxService outboxService,
            CustomerResponseMapper responseMapper,
            @Autowired(required = false) CustomerMetrics customerMetrics) {
        this.customerRepository = customerRepository;
        this.passwordEncoder = passwordEncoder;
        this.jwtService = jwtService;
        this.outboxService = outboxService;
        this.responseMapper = responseMapper;
        this.customerMetrics = customerMetrics;
    }

    @Override
    @Transactional
    public AuthResponse handle(RegisterCommand command) {
        RegisterRequest request = command.request();
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

        return AuthResponse.of(accessToken, refreshToken, jwtService.getAccessTokenExpirationSeconds(), responseMapper.toCustomerResponse(saved));
    }
}
