package com.dgl.customer.cqrs.handler;

import com.dgl.customer.config.CustomerMetrics;
import com.dgl.customer.cqrs.CommandHandler;
import com.dgl.customer.cqrs.command.UpdateCustomerCommand;
import com.dgl.customer.cqrs.mapper.CustomerResponseMapper;
import com.dgl.customer.domain.Customer;
import com.dgl.customer.dto.request.UpdateCustomerRequest;
import com.dgl.customer.dto.response.CustomerResponse;
import com.dgl.customer.exception.CustomerNotFoundException;
import com.dgl.customer.messaging.event.CustomerUpdatedPayload;
import com.dgl.customer.outbox.OutboxService;
import com.dgl.customer.repository.CustomerRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Component
public class UpdateCustomerCommandHandler implements CommandHandler<UpdateCustomerCommand, CustomerResponse> {

    private final CustomerRepository customerRepository;
    private final OutboxService outboxService;
    private final CustomerResponseMapper responseMapper;
    private final CustomerMetrics customerMetrics;

    public UpdateCustomerCommandHandler(
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
    public CustomerResponse handle(UpdateCustomerCommand command) {
        UUID id = command.id();
        UpdateCustomerRequest request = command.request();

        Customer customer = customerRepository.findById(id)
                .orElseThrow(() -> new CustomerNotFoundException(id));

        customer.setFirstName(request.firstName().trim());
        customer.setLastName(request.lastName().trim());
        if (request.phoneNumber() != null) {
            customer.setPhoneNumber(request.phoneNumber().trim());
        }
        if (request.status() != null) {
            customer.setStatus(request.status());
        }

        outboxService.recordEvent(
                "Customer",
                customer.getId().toString(),
                "CustomerUpdated",
                UUID.randomUUID(),
                null,
                new CustomerUpdatedPayload(
                        customer.getId(),
                        customer.getEmail(),
                        customer.getFirstName(),
                        customer.getLastName(),
                        customer.getPhoneNumber(),
                        customer.getStatus().name()
                )
        );

        if (customerMetrics != null) {
            customerMetrics.incrementUpdated();
        }

        return responseMapper.toCustomerResponse(customer);
    }
}
