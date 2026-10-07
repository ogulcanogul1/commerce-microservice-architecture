package com.dgl.customer.repository;

import com.dgl.customer.domain.CustomerPreferences;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.UUID;

@Repository
public interface CustomerPreferencesRepository extends JpaRepository<CustomerPreferences, UUID> {
}
