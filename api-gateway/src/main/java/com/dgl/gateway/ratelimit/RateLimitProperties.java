package com.dgl.gateway.ratelimit;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

/**
 * Gateway hız sınırlayıcı (Rate Limiter) yapılandırma özellikleri.
 * application.yaml altındaki "rate-limiter" önekine bağlanır.
 */
@Getter
@Setter
@Component
@ConfigurationProperties(prefix = "rate-limiter")
public class RateLimitProperties {

    /**
     * Hız sınırlayıcının genel olarak devrede olup olmadığı.
     */
    private boolean enabled = true;

    /**
     * X-Forwarded-For başlığına güvenilip güvenilmeyeceği.
     * Güvenli olmayan ortamlarda IP sahteciliğini önlemek için varsayılan: false (yalnızca request.getRemoteAddr() kullanılır).
     */
    private boolean trustForwardedFor = false;

    /**
     * Özel rota bazlı hız sınırlama politikaları listesi.
     */
    private List<RateLimitPolicy> policies = new ArrayList<>();
}
