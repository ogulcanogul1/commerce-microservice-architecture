from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InstanceInfo:
    """Eureka Service Registry için mikroservis instance (örnek) kimlik ve adres modeli.

    Bu model, Netflix Eureka REST API v2 spesifikasyonuna uygun JSON zarfını üretir.
    Neden frozen=True?
    - Instance bilgileri (IP, port, ID) çalışma zamanında değişmeyen değişmez (immutable)
      özelliktedir. Thread-safe ve öngörülebilir olmasını sağlar.
    """

    # Eureka standartlarında uygulama isimleri geleneksel olarak BÜYÜK HARFLE tutulur (Örn: "AI-ASSISTANT-SERVICE")
    app_name: str

    # Eureka kümesinde her bir replikayı benzersiz tanımlayan kimlik (Örn: "192.168.1.50:ai-assistant-service:8089")
    # IP tabanlı olması, aynı makinede veya farklı konteynerlerde çalışan replikaların birbirini ezmesini engeller.
    instance_id: str

    # Gateway ve diğer servislerin bağlanacağı host adı veya IP
    host: str

    # Mikroservisin doğrudan IP adresi (DNS bağımlılığı olmadan hızlı erişim sağlar)
    ip_addr: str

    # Mikroservisin dinlediği HTTP port numarası (varsayılan: 8089)
    port: int

    # Eureka'nın ve Gateway'in servisin canlılığını kontrol edeceği uç nokta (http://host:8089/health)
    health_url: str

    # Servisin Eureka'ya ne sıklıkla 'hayattayım' nabzı (heartbeat) göndereceği (saniye, varsayılan 10)
    renewal_sec: int = 10

    # Eureka'nın nabız kesildiğinde servisi 'ölü' sayıp kayıttan düşüreceği süre (saniye, varsayılan 30)
    lease_sec: int = 30

    def to_payload(self) -> dict[str, Any]:
        """Eureka REST API'sinin (POST /eureka/apps/{APP}) beklediği standart JSON zarfını üretir.

        Eureka Şeması Hakkında Kritik Bilgiler:
        - `vipAddress` ve `secureVipAddress`: Spring Cloud Gateway'in `lb://ai-assistant-service`
          yönlendirmesinde kullandığı mantıksal servis adıdır (küçük harfle verilir).
        - `dataCenterInfo`: AWS dışındaki yerel (on-premise/docker) sunucular için
          'com.netflix.appinfo.InstanceInfo$DefaultDataCenterInfo' ve 'MyOwn' olmak zorundadır.
        - `port` ve `securePort`: Eureka XML/JSON protokolü gereği integer değeri `$` anahtarıyla,
          aktiflik durumunu `@enabled` string anahtarıyla taşır.
        """
        return {
            "instance": {
                "instanceId": self.instance_id,
                "hostName": self.host,
                "app": self.app_name,
                "ipAddr": self.ip_addr,
                # Spring Cloud Gateway loadbalancer bu vipAddress ile servis örneklerini bulur:
                "vipAddress": self.app_name.lower(),
                "secureVipAddress": self.app_name.lower(),
                "status": "UP",
                "port": {"$": self.port, "@enabled": "true"},
                "securePort": {"$": 443, "@enabled": "false"},
                "healthCheckUrl": self.health_url,
                "statusPageUrl": self.health_url,
                "homePageUrl": f"http://{self.host}:{self.port}/",
                "dataCenterInfo": {
                    "@class": "com.netflix.appinfo.InstanceInfo$DefaultDataCenterInfo",
                    "name": "MyOwn",
                },
                "leaseInfo": {
                    "renewalIntervalInSecs": self.renewal_sec,
                    "durationInSecs": self.lease_sec,
                },
                "metadata": {
                    "language": "python",
                    "framework": "fastapi",
                    "management.port": str(self.port),
                },
            }
        }
