package com.dgl.customer.cqrs.handler;

import com.dgl.customer.cqrs.CommandHandler;
import com.dgl.customer.cqrs.command.UpdatePreferencesCommand;
import com.dgl.customer.cqrs.mapper.CustomerResponseMapper;
import com.dgl.customer.domain.Customer;
import com.dgl.customer.domain.CustomerPreferences;
import com.dgl.customer.dto.request.UpdatePreferencesRequest;
import com.dgl.customer.dto.response.PreferencesResponse;
import com.dgl.customer.exception.CustomerNotFoundException;
import com.dgl.customer.repository.CustomerPreferencesRepository;
import com.dgl.customer.repository.CustomerRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Component
@RequiredArgsConstructor
public class UpdatePreferencesCommandHandler implements CommandHandler<UpdatePreferencesCommand, PreferencesResponse> {

    private final CustomerRepository customerRepository;
    private final CustomerPreferencesRepository preferencesRepository;
    private final CustomerResponseMapper responseMapper;

    @Override
    @Transactional
    public PreferencesResponse handle(UpdatePreferencesCommand command) {
        UUID customerId = command.customerId();
        UpdatePreferencesRequest request = command.request();

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
        return responseMapper.toPreferencesResponse(savedPrefs);
    }
}
