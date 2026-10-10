package com.dgl.customer.cqrs.mapper;

import com.dgl.customer.domain.Customer;
import com.dgl.customer.domain.CustomerAddress;
import com.dgl.customer.domain.CustomerPreferences;
import com.dgl.customer.dto.response.AddressResponse;
import com.dgl.customer.dto.response.CustomerResponse;
import com.dgl.customer.dto.response.PreferencesResponse;
import org.springframework.stereotype.Component;

@Component
public class CustomerResponseMapper {

    public CustomerResponse toCustomerResponse(Customer customer) {
        if (customer == null) {
            return null;
        }

        PreferencesResponse prefsResponse = customer.getPreferences() != null
                ? toPreferencesResponse(customer.getPreferences())
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

    public PreferencesResponse toPreferencesResponse(CustomerPreferences preferences) {
        if (preferences == null) {
            return null;
        }

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

    public AddressResponse toAddressResponse(CustomerAddress address) {
        if (address == null) {
            return null;
        }

        return new AddressResponse(
                address.getId(),
                address.getCustomer().getId(),
                address.getTitle(),
                address.getAddressLine1(),
                address.getAddressLine2(),
                address.getCity(),
                address.getDistrict(),
                address.getPostalCode(),
                address.getCountry(),
                address.isDefault(),
                address.getCreatedAt(),
                address.getUpdatedAt()
        );
    }
}
