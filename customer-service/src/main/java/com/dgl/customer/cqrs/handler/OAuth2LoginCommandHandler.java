package com.dgl.customer.cqrs.handler;

import com.dgl.customer.config.CustomerMetrics;
import com.dgl.customer.cqrs.CommandHandler;
import com.dgl.customer.cqrs.command.OAuth2LoginCommand;
import com.dgl.customer.cqrs.mapper.CustomerResponseMapper;
import com.dgl.customer.domain.Customer;
import com.dgl.customer.domain.CustomerPreferences;
import com.dgl.customer.domain.CustomerStatus;
import com.dgl.customer.domain.Role;
import com.dgl.customer.dto.request.OAuth2LoginRequest;
import com.dgl.customer.dto.response.AuthResponse;
import com.dgl.customer.messaging.event.CustomerCreatedPayload;
import com.dgl.customer.outbox.OutboxService;
import com.dgl.customer.repository.CustomerRepository;
import com.dgl.customer.service.JwtService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.UUID;

@Slf4j
@Component
public class OAuth2LoginCommandHandler implements CommandHandler<OAuth2LoginCommand, AuthResponse> {

    private final CustomerRepository customerRepository;
    private final JwtService jwtService;
    private final OutboxService outboxService;
    private final CustomerResponseMapper responseMapper;
    private final CustomerMetrics customerMetrics;

    public OAuth2LoginCommandHandler(
            CustomerRepository customerRepository,
            JwtService jwtService,
            OutboxService outboxService,
            CustomerResponseMapper responseMapper,
            @Autowired(required = false) CustomerMetrics customerMetrics) {
        this.customerRepository = customerRepository;
        this.jwtService = jwtService;
        this.outboxService = outboxService;
        this.responseMapper = responseMapper;
        this.customerMetrics = customerMetrics;
    }

    @Override
    @Transactional
    public AuthResponse handle(OAuth2LoginCommand command) {
        OAuth2LoginRequest request = command.request();
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

        return AuthResponse.of(accessToken, refreshToken, jwtService.getAccessTokenExpirationSeconds(), responseMapper.toCustomerResponse(customer));
    }
}
