"""Mikroservis ağ ve IP çözümleme modülü.

Bu modül, mikroservis ayağa kalktığında Eureka Service Registry'ye bildirilecek
olan (host, ip) ikilisini dinamik olarak tespit eder.
"""

import socket


def resolve_instance_host(
    configured_host: str = "",
    prefer_ip: bool = True,
) -> tuple[str, str]:
    """Mikroservis örneğinin Eureka'ya bildireceği (host, ip) ikilisini belirler.

    Eureka, kendisine kaydolan her servis için iki temel adres bilgisi ister:
    1. hostName : Servisin adı veya IP'si (örn: '192.168.1.50' veya 'ai-service-1')
    2. ipAddr   : Servisin kesin IPv4 adresi (örn: '192.168.1.50')

    Parametreler:
        configured_host: Ortam değişkeninden (SERVICE_HOST) gelen manuel host/IP.
                         Boşsa otomatik yerel makine/container IP'si tespit edilir.
        prefer_ip:       True ise 'hostName' alanına da IP yazılır. Böylece API Gateway
                         ve diğer servisler DNS sorgusu beklemeden doğrudan IP üzerinden
                         iletişim kurar (ağ gecikmesini ve DNS hatalarını önler).

    Dönen Değer:
        (host, ip) ikilisi. Örn: ("192.168.1.50", "192.168.1.50")
    """
    clean_host = configured_host.strip()

    # DURUM 1: Kullanıcı ortam değişkeninden (SERVICE_HOST) özel bir host adı veya IP vermişse
    if clean_host:
        try:
            # socket.gethostbyname(clean_host):
            # İşletim sisteminin DNS sistemine sorar: "Bu host adının arkasındaki gerçek IPv4 nedir?"
            # Örnek 1: 'ai-host.local' verilmişse -> DNS'ten '192.168.1.15' olarak çözer.
            # Örnek 2: Zaten doğrudan '192.168.1.15' verilmişse -> Aynen IP olarak döner.
            resolved_ip = socket.gethostbyname(clean_host)
        except OSError:
            # DNS sunucusuna ulaşılamazsa veya host adı DNS'te kayıtlı değilse program çökmesin diye:
            # Verilen metni doğrudan IP kabul edip devam ediyoruz (fallback).
            resolved_ip = clean_host

        host = clean_host
        ip = resolved_ip

    # DURUM 2: SERVICE_HOST boş bırakılmışsa (varsayılan ve en yaygın senaryo - Docker/Yerel)
    else:
        try:
            # 1. Adım: Çalıştığımız makinenin/container'ın yerel bilgisayar adını al (örn: 'e3b0c44298fc')
            hostname = socket.gethostname()
            # 2. Adım: Bu hostname'i yerel ağdaki gerçek IPv4 adresine dönüştür (örn: '172.18.0.4')
            ip = socket.gethostbyname(hostname)
        except OSError:
            # Ağ arayüzü henüz hazır değilse veya DNS çözülemezse güvenli fallback olarak localhost ver
            ip = "127.0.0.1"

        host = ip

    # EUREKA_PREFER_IP kontrolü:
    # Mikroservis mimarilerinde (Spring Cloud / Eureka) en iyi pratik "prefer-ip-address=true"dur.
    # Çünkü container adları ('ai-assistant-service-1') her zaman DNS üzerinden çözülemeyebilir.
    # IP tercih edilmişse host bilgisini de doğrudan çözülen IP ile eşitliyoruz.
    if prefer_ip:
        host = ip

    return host, ip
