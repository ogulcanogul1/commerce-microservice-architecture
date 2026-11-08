package com.dgl.gateway.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.restclient.RestClientCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;

import java.time.Duration;

/**
 * Spring Cloud Gateway Server WebMVC HTTP istemcisi yapılandırması.
 * En uzun AI TimeLimiter süresinden (70s) daha uzun bir read-timeout (80s) tanımlayarak
 * arka uç soketinin erken kopmasını engeller (Adım 7d).
 */
@Configuration
public class GatewayHttpClientConfig {

    @Bean
    public RestClientCustomizer aiGatewayRestClientTimeoutCustomizer(
            @Value("${gateway.http-client.read-timeout:80s}") Duration readTimeout,
            @Value("${gateway.http-client.connect-timeout:10s}") Duration connectTimeout) {
        return restClientBuilder -> {
            SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
            requestFactory.setConnectTimeout((int) connectTimeout.toMillis());
            requestFactory.setReadTimeout((int) readTimeout.toMillis());
            restClientBuilder.requestFactory(requestFactory);
        };
    }
}
