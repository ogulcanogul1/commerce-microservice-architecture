package com.dgl.customer.service;

import com.dgl.customer.domain.Customer;
import com.dgl.customer.domain.CustomerPreferences;
import com.dgl.customer.domain.CustomerStatus;
import com.dgl.customer.dto.request.CreateCustomerRequest;
import com.dgl.customer.dto.request.UpdateCustomerRequest;
import com.dgl.customer.dto.request.UpdatePreferencesRequest;
import com.dgl.customer.dto.response.CustomerResponse;
import com.dgl.customer.dto.response.PreferencesResponse;
import com.dgl.customer.exception.CustomerNotFoundException;
import com.dgl.customer.exception.EmailAlreadyExistsException;
import com.dgl.customer.repository.CustomerPreferencesRepository;
import com.dgl.customer.repository.CustomerRepository;
import com.dgl.customer.messaging.event.CustomerCreatedPayload;
import com.dgl.customer.messaging.event.CustomerUpdatedPayload;
import com.dgl.customer.outbox.OutboxService;
import com.dgl.customer.config.CustomerMetrics;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.UUID;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class CustomerServiceImpl implements CustomerService {

    private final CustomerRepository customerRepository;
    private final CustomerPreferencesRepository preferencesRepository;
    private final OutboxService outboxService;

    @Autowired(required = false)
    private CustomerMetrics customerMetrics;

    @Override
    @Transactional
    public CustomerResponse createCustomer(CreateCustomerRequest request) {
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

        return mapToResponse(saved);
    }

    @Override
    @Transactional
    public CustomerResponse updateCustomer(UUID id, UpdateCustomerRequest request) {
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

        return mapToResponse(customer);
    }

    @Override
    public CustomerResponse getCustomerById(UUID id) {
        Customer customer = customerRepository.findById(id)
                .orElseThrow(() -> new CustomerNotFoundException(id));
        return mapToResponse(customer);
    }

    @Override
    public CustomerResponse getCustomerByEmail(String email) {
        Customer customer = customerRepository.findByEmail(email.toLowerCase().trim())
                .orElseThrow(() -> new CustomerNotFoundException("Customer not found with email: " + email));
        return mapToResponse(customer);
    }

    @Override
    public Page<CustomerResponse> getAllCustomers(Pageable pageable) {
        return customerRepository.findAll(pageable)
                .map(this::mapToResponse);
    }

    @Override
    @Transactional
    public PreferencesResponse updatePreferences(UUID customerId, UpdatePreferencesRequest request) {
        Customer customer = customerRepository.findById(customerId)
                .orElseThrow(() -> new CustomerNotFoundException(customerId));

        CustomerPreferences prefs = customer.getPreferences();
        if (prefs == null) {
            prefs = CustomerPreferences.builder()
                    .customer(customer)
                    .build();
            customer.setPreferences(prefs);
        }

        if (request.emailNotifications() != null) {
            prefs.setEmailNotifications(request.emailNotifications());
        }
        if (request.smsNotifications() != null) {
            prefs.setSmsNotifications(request.smsNotifications());
        }
        if (request.pushNotifications() != null) {
            prefs.setPushNotifications(request.pushNotifications());
        }
        if (request.language() != null && !request.language().isBlank()) {
            prefs.setLanguage(request.language().trim());
        }
        if (request.currency() != null && !request.currency().isBlank()) {
            prefs.setCurrency(request.currency().trim());
        }

        CustomerPreferences savedPrefs = preferencesRepository.save(prefs);
        return mapPreferencesToResponse(savedPrefs);
    }

    private CustomerResponse mapToResponse(Customer customer) {
        PreferencesResponse prefsResponse = customer.getPreferences() != null
                ? mapPreferencesToResponse(customer.getPreferences())
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

    private PreferencesResponse mapPreferencesToResponse(CustomerPreferences preferences) {
        return new PreferencesResponse(
                preferences.getCustomerId(),
                preferences.isEmailNotifications(),
                preferences.isSmsNotifications(),
                preferences.isPushNotifications(),
                preferences.getLanguage(),
                preferences.getCurrency(),
                preferences.getUpdatedAt()
        );
    }
}
