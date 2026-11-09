"""Production başlangıç güvenlik denetimi.

Dev ortamında varsayılan secret yalnızca uyarı üretir; dev dışı ortamlarda zayıf
yapılandırma servisin açılmasını engeller (fail-fast).
"""

import logging

logger = logging.getLogger(__name__)

# Bu ortamlarda zayıf yapılandırma uyarı üretir, servisi durdurmaz.
DEV_ENVIRONMENTS = frozenset({"development", "dev", "local", "test"})

# Repoda, compose'ta ve Java varsayılanlarında geçen herkesçe bilinen değer.
KNOWN_DEFAULT_SECRET = "dgl-internal-gateway-secret-token-2026"
MIN_SECRET_LENGTH = 32


def collect_security_problems(
    *,
    environment: str,
    gateway_security_enabled: bool,
    gateway_secret: str,
    ticket_publisher: str,
) -> list[str]:
    """Güvensiz yapılandırma sorunlarını döndürür (boş liste = sorun yok).

    Secret değerinin kendisi mesajlara YAZILMAZ.
    """
    problems: list[str] = []
    if not gateway_security_enabled:
        problems.append("GATEWAY_SECURITY_ENABLED=false: gateway secret doğrulaması kapalı")
    if gateway_secret == KNOWN_DEFAULT_SECRET:
        problems.append("GATEWAY_INTERNAL_SECRET varsayılan (repoda bilinen) değerde")
    elif len(gateway_secret) < MIN_SECRET_LENGTH:
        problems.append(f"GATEWAY_INTERNAL_SECRET {MIN_SECRET_LENGTH} karakterden kısa")
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
    """Dev dışı ortamda sorun varsa RuntimeError fırlatır; dev'de yalnızca uyarır."""
    problems = collect_security_problems(
        environment=environment,
        gateway_security_enabled=gateway_security_enabled,
        gateway_secret=gateway_secret,
        ticket_publisher=ticket_publisher,
    )
    if not problems:
        return
    if environment.strip().lower() in DEV_ENVIRONMENTS:
        for problem in problems:
            logger.warning("Güvenlik uyarısı (%s ortamı, durdurulmadı): %s", environment, problem)
        return
    raise RuntimeError("Güvensiz yapılandırma, servis başlatılmadı: " + "; ".join(problems))
