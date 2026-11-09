package com.dgl.config;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.config.environment.Environment;
import org.springframework.cloud.config.environment.PropertySource;
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

    @Test
    void shouldServeAiAssistantRuntimeKeysWithProfilePrecedence() {
        Environment environment = environmentRepository.findOne("ai-assistant-service", "prod", null);
        assertThat(environment).isNotNull();

        List<PropertySource> sources = environment.getPropertySources();
        int prodIndex = indexOf(sources, "ai-assistant-service-prod.yaml");
        int baseIndex = indexOf(sources, "ai-assistant-service.yaml");

        // propertySources en yüksek öncelik başta: prod dosyası temel dosyadan ÖNCE gelmeli
        assertThat(prodIndex).isGreaterThanOrEqualTo(0).isLessThan(baseIndex);
        assertThat(sources.get(baseIndex).getSource().containsKey("ai.agent.max-steps")).isTrue();
        assertThat(sources.get(prodIndex).getSource().containsKey("ai.logging.level")).isTrue();
    }

    private static int indexOf(List<PropertySource> sources, String fileName) {
        for (int i = 0; i < sources.size(); i++) {
            if (sources.get(i).getName().contains(fileName)) {
                return i;
            }
        }
        return -1;
    }
}
