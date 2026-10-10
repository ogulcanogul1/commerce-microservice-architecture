package com.dgl.customer.cqrs.handler;

import com.dgl.customer.cqrs.CommandHandler;
import com.dgl.customer.cqrs.command.LoginCommand;
import com.dgl.customer.cqrs.mapper.CustomerResponseMapper;
import com.dgl.customer.domain.Customer;
import com.dgl.customer.domain.CustomerStatus;
import com.dgl.customer.dto.request.LoginRequest;
import com.dgl.customer.dto.response.AuthResponse;
import com.dgl.customer.exception.InvalidCredentialsException;
import com.dgl.customer.repository.CustomerRepository;
import com.dgl.customer.service.JwtService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Slf4j
@Component
@RequiredArgsConstructor
public class LoginCommandHandler implements CommandHandler<LoginCommand, AuthResponse> {

    private final CustomerRepository customerRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtService jwtService;
    private final CustomerResponseMapper responseMapper;

    @Override
    @Transactional(readOnly = true)
    public AuthResponse handle(LoginCommand command) {
        LoginRequest request = command.request();
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

        return AuthResponse.of(accessToken, refreshToken, jwtService.getAccessTokenExpirationSeconds(), responseMapper.toCustomerResponse(customer));
    }
}
