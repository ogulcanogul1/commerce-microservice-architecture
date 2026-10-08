package com.dgl.customer.outbox;

import com.dgl.customer.domain.Customer;
import com.dgl.customer.domain.CustomerStatus;
import com.dgl.customer.dto.request.CreateCustomerRequest;
import com.dgl.customer.dto.request.UpdateCustomerRequest;
import com.dgl.customer.dto.response.CustomerResponse;
import com.dgl.customer.repository.CustomerAddressRepository;
import com.dgl.customer.repository.CustomerPreferencesRepository;
import com.dgl.customer.repository.CustomerRepository;
import com.dgl.customer.service.CustomerService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.test.context.EmbeddedKafka;
import org.springframework.test.annotation.DirtiesContext;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@DirtiesContext
@EmbeddedKafka(
        partitions = 1,
        topics = {
                "customers.created",
                "customers.updated"
        }
)
class CustomerOutboxIntegrationTest {

    @Autowired
    private CustomerService customerService;

    @Autowired
    private CustomerRepository customerRepository;

    @Autowired
    private CustomerAddressRepository addressRepository;

    @Autowired
    private CustomerPreferencesRepository preferencesRepository;

    @Autowired
    private OutboxEventRepository outboxEventRepository;

    @Autowired
    private OutboxPoller outboxPoller;

    @BeforeEach
    void setUp() {
        outboxEventRepository.deleteAll();
        addressRepository.deleteAll();
        preferencesRepository.deleteAll();
        customerRepository.deleteAll();
    }

    @Test
    @DisplayName("Transactional Outbox: createCustomer and updateCustomer should persist outbox events and poller should publish them to Kafka")
    void createAndUpdateCustomer_ShouldPersistOutboxAndPollerShouldPublish() {
        // 1. Create customer
        CreateCustomerRequest createRequest = new CreateCustomerRequest(
                "customer.outbox@example.com",
                "Jane",
                "Doe",
                "+905553334455"
        );

        CustomerResponse created = customerService.createCustomer(createRequest);

        assertThat(created).isNotNull();
        assertThat(customerRepository.existsById(created.id())).isTrue();

        List<OutboxEvent> createEvents = outboxEventRepository.findAll();
        assertThat(createEvents).hasSize(1);

        OutboxEvent createEvent = createEvents.getFirst();
        assertThat(createEvent.getStatus()).isEqualTo(OutboxStatus.PENDING);
        assertThat(createEvent.getAggregateType()).isEqualTo("Customer");
        assertThat(createEvent.getAggregateId()).isEqualTo(created.id().toString());
        assertThat(createEvent.getType()).isEqualTo("CustomerCreated");
        assertThat(createEvent.getPayload()).contains("customer.outbox@example.com");

        // Execute poller
        outboxPoller.pollAndPublish();

        // Verify published
        OutboxEvent publishedCreateEvent = outboxEventRepository.findById(createEvent.getId()).orElseThrow();
        assertThat(publishedCreateEvent.getStatus()).isEqualTo(OutboxStatus.PUBLISHED);
        assertThat(publishedCreateEvent.getProcessedAt()).isNotNull();

        // 2. Update customer
        outboxEventRepository.deleteAll();

        UpdateCustomerRequest updateRequest = new UpdateCustomerRequest(
                "JaneUpdated",
                "DoeUpdated",
                "+905559990000",
                CustomerStatus.ACTIVE
        );

        customerService.updateCustomer(created.id(), updateRequest);

        List<OutboxEvent> updateEvents = outboxEventRepository.findAll();
        assertThat(updateEvents).hasSize(1);

        OutboxEvent updateEvent = updateEvents.getFirst();
        assertThat(updateEvent.getStatus()).isEqualTo(OutboxStatus.PENDING);
        assertThat(updateEvent.getType()).isEqualTo("CustomerUpdated");
        assertThat(updateEvent.getPayload()).contains("JaneUpdated");

        // Execute poller
        outboxPoller.pollAndPublish();

        // Verify published
        OutboxEvent publishedUpdateEvent = outboxEventRepository.findById(updateEvent.getId()).orElseThrow();
        assertThat(publishedUpdateEvent.getStatus()).isEqualTo(OutboxStatus.PUBLISHED);
        assertThat(publishedUpdateEvent.getProcessedAt()).isNotNull();

        Customer customer = customerRepository.findById(created.id()).orElseThrow();
        assertThat(customer.getFirstName()).isEqualTo("JaneUpdated");
    }
}
