package com.dgl.customer.cqrs.handler;

import com.dgl.customer.config.CustomerMetrics;
import com.dgl.customer.cqrs.CommandHandler;
import com.dgl.customer.cqrs.command.CreateCustomerCommand;
import com.dgl.customer.cqrs.mapper.CustomerResponseMapper;
import com.dgl.customer.domain.Customer;
import com.dgl.customer.domain.CustomerPreferences;
import com.dgl.customer.domain.CustomerStatus;
import com.dgl.customer.dto.request.CreateCustomerRequest;
import com.dgl.customer.dto.response.CustomerResponse;
import com.dgl.customer.exception.EmailAlreadyExistsException;
import com.dgl.customer.messaging.event.CustomerCreatedPayload;
import com.dgl.customer.outbox.OutboxService;
import com.dgl.customer.repository.CustomerRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.UUID;

@Component
public class CreateCustomerCommandHandler implements CommandHandler<CreateCustomerCommand, CustomerResponse> {

    private final CustomerRepository customerRepository;
    private final OutboxService outboxService;
    private final CustomerResponseMapper responseMapper;
    private final CustomerMetrics customerMetrics;

    public CreateCustomerCommandHandler(
            CustomerRepository customerRepository,
            OutboxService outboxService,
            CustomerResponseMapper responseMapper,
            @Autowired(required = false) CustomerMetrics customerMetrics) {
        this.customerRepository = customerRepository;
        this.outboxService = outboxService;
        this.responseMapper = responseMapper;
        this.customerMetrics = customerMetrics;
    }

    @Override
    @Transactional
    public CustomerResponse handle(CreateCustomerCommand command) {
        CreateCustomerRequest request = command.request();
        if (customerRepository.existsByEmail(request.email())) {
            throw new EmailAlreadyExistsException("Customer with email '" + request.email() + "' already exists");
        }

        Customer customer = Customer.builder()
                .email(request.email().toLowerCase().trim())
                .firstName(request.firstName().trim())
                .lastName(request.lastName().trim())
                .phoneNumber(request.phoneNumber())
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

        return responseMapper.toCustomerResponse(saved);
    }
}
