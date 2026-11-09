"""Production başlangıç güvenlik denetimi (Startup Security Checks).

Bu modül, mikroservisin ayağa kalkma (startup) anında kritik güvenlik ayarlarını denetler.
- Geliştirme ortamında (development/dev/local/test) zayıf konfigürasyon tespit edilirse loglara uyarı (WARNING) basar ama servisi durdurmaz.
- Canlı/Üretim ortamında (production/prod/staging) zayıf veya varsayılan secret tespit edilirse 'Fail-Fast' prensibi gereği
  servisin başlamasını engeller (RuntimeError fırlatarak çöker). Böylece güvensiz bir servisin canlıya çıkması önlenir.
"""

import logging

logger = logging.getLogger(__name__)

# Geliştirme ve test ortamları: Bu ortamlarda zayıf yapılandırma olsa dahi servis açılır, sadece uyarı loglanır.
DEV_ENVIRONMENTS = frozenset({"development", "dev", "local", "test"})

# Git reposunda, docker-compose dosyalarında ve Java varsayılanlarında açıkça yazılı olan güvensiz token.
# Üretim ortamında bu değerin mutlaka rastgele güçlü bir secret ile ezilmesi zorunludur.
KNOWN_DEFAULT_SECRET = "dgl-internal-gateway-secret-token-2026"

# Kaba kuvvet (brute-force) saldırılarına karşı en az 256-bit entropiye denk gelen asgari karakter uzunluğu.
MIN_SECRET_LENGTH = 32


def collect_security_problems(
    *,
    environment: str,
    gateway_security_enabled: bool,
    gateway_secret: str,
    ticket_publisher: str,
) -> list[str]:
    """Sistemdeki potansiyel güvenlik açıklarını toplayıp bir liste olarak döndürür.

    Denetlenen Kurallar:
    1. GATEWAY_SECURITY_ENABLED: False ise servis Gateway bypass korumasız kalır (herkes doğrudan çağırabilir).
    2. GATEWAY_INTERNAL_SECRET: Repodaki bilinen varsayılan token ile aynıysa yetkisiz kişiler sahte header gönderebilir.
    3. Secret Uzunluğu: 32 karakterden kısaysa yeterince güvenli değildir.
    4. TICKET_PUBLISHER: Canlıda 'kafka' olmalıdır; aksi halde üretilen biletler bir yere yazılmadan kaybolur.

    ÖNEMLİ GÜVENLİK KURALI:
    Oluşturulan hata mesajlarının içine asla gerçek secret değeri YAZILMAZ (loglara sızmaması için).
    """
    problems: list[str] = []

    # 1. Kontrol: Ağ geçidi çevre güvenliği kapalı mı?
    if not gateway_security_enabled:
        problems.append("GATEWAY_SECURITY_ENABLED=false: gateway secret doğrulaması kapalı")

    # 2. Kontrol: Varsayılan zayıf secret mı kullanılıyor?
    if gateway_secret == KNOWN_DEFAULT_SECRET:
        problems.append("GATEWAY_INTERNAL_SECRET varsayılan (repoda bilinen) değerde")
    # 3. Kontrol: Secret karakter uzunluğu yeterli mi?
    elif len(gateway_secret) < MIN_SECRET_LENGTH:
        problems.append(f"GATEWAY_INTERNAL_SECRET {MIN_SECRET_LENGTH} karakterden kısa")

    # 4. Kontrol: Müşteri destek talepleri mesaj kuyruğuna (Kafka) gidiyor mu?
    if ticket_publisher != "kafka":
        problems.append(
            "TICKET_PUBLISHER=kafka değil: destek talepleri hiçbir yere iletilmez "
            "ama müşteriye 'oluşturuldu' denir"
        )

    return problems


def enforce_security_startup(
    *,
    environment: str,
    gateway_security_enabled: bool,
    gateway_secret: str,
    ticket_publisher: str,
) -> None:
    """Açılışta güvenlik kurallarını zorunlu kılar (Enforce Security Startup).

    - Canlı (production) ortamda tek bir güvenlik problemi dahi varsa RuntimeError fırlatır (Fail-Fast).
    - Geliştirme (development) ortamında ise geliştiriciyi engellememek için problemleri WARNING seviyesinde loglar.
    """
    # Mevcut ortamdaki güvenlik zafiyetlerini tara
    problems = collect_security_problems(
        environment=environment,
        gateway_security_enabled=gateway_security_enabled,
        gateway_secret=gateway_secret,
        ticket_publisher=ticket_publisher,
    )

    # Hiçbir güvenlik sorunu yoksa açılışa güvenle devam et
    if not problems:
        return

    # Eğer geliştirme/test ortamındaysak servisi kapatma, sadece geliştiriciyi uyar
    if environment.strip().lower() in DEV_ENVIRONMENTS:
        for problem in problems:
            logger.warning("Güvenlik uyarısı (%s ortamı, durdurulmadı): %s", environment, problem)
        return

    # Canlı ortamdaysak güvensiz konfigürasyonla servisin açılmasına kesinlikle izin verme (Fail-Fast)
    raise RuntimeError("Güvensiz yapılandırma, servis başlatılmadı: " + "; ".join(problems))
