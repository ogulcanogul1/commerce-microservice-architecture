package com.dgl.config;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.config.environment.Environment;
import org.springframework.cloud.config.server.environment.EnvironmentRepository;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
    "eureka.client.enabled=false",
    "eureka.client.register-with-eureka=false",
    "eureka.client.fetch-registry=false"
})
class ConfigServerApplicationTests {

    @Autowired
    private EnvironmentRepository environmentRepository;

    @Test
    void contextLoads() {
        assertThat(environmentRepository).isNotNull();
    }

    @Test
    void shouldFindServiceSpecificAndCommonConfigurations() {
        Environment environment = environmentRepository.findOne("order-service", "dev", null);

        assertThat(environment).isNotNull();
        assertThat(environment.getName()).isEqualTo("order-service");
        assertThat(environment.getProfiles()).contains("dev");

        // Verify that PropertySources from both directory-per-service and common are loaded
        boolean hasOrderConfig = environment.getPropertySources().stream()
                .anyMatch(ps -> ps.getName().contains("order-service"));
        boolean hasCommonConfig = environment.getPropertySources().stream()
                .anyMatch(ps -> ps.getName().contains("application"));

        assertThat(hasOrderConfig).isTrue();
        assertThat(hasCommonConfig).isTrue();
    }
}
