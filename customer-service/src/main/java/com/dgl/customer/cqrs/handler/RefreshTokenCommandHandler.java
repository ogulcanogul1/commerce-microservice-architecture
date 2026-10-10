package com.dgl.customer.cqrs.handler;

import com.dgl.customer.cqrs.CommandHandler;
import com.dgl.customer.cqrs.command.RefreshTokenCommand;
import com.dgl.customer.cqrs.mapper.CustomerResponseMapper;
import com.dgl.customer.domain.Customer;
import com.dgl.customer.domain.CustomerStatus;
import com.dgl.customer.dto.request.RefreshTokenRequest;
import com.dgl.customer.dto.response.AuthResponse;
import com.dgl.customer.exception.InvalidTokenException;
import com.dgl.customer.repository.CustomerRepository;
import com.dgl.customer.service.JwtService;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Component
@RequiredArgsConstructor
public class RefreshTokenCommandHandler implements CommandHandler<RefreshTokenCommand, AuthResponse> {

    private final CustomerRepository customerRepository;
    private final JwtService jwtService;
    private final CustomerResponseMapper responseMapper;

    @Override
    @Transactional(readOnly = true)
    public AuthResponse handle(RefreshTokenCommand command) {
        RefreshTokenRequest request = command.request();

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

        return AuthResponse.of(newAccessToken, newRefreshToken, jwtService.getAccessTokenExpirationSeconds(), responseMapper.toCustomerResponse(customer));
    }
}
