"""Başlangıç güvenlik denetimi birim testleri."""

import pytest

from app.core.startup_checks import (
    DEV_ENVIRONMENTS,
    KNOWN_DEFAULT_SECRET,
    collect_security_problems,
    enforce_security_startup,
)


def test_dev_environment_with_default_secret_only_warns():
    """Development ortamında bilinen secret ile RuntimeError fırlatılmaz, sadece uyarılır."""
    enforce_security_startup(
        environment="development",
        gateway_security_enabled=True,
        gateway_secret=KNOWN_DEFAULT_SECRET,
        ticket_publisher="kafka",
    )


def test_production_with_default_secret_raises():
    """Production ortamında bilinen secret ile servis açılmamalıdır."""
    with pytest.raises(RuntimeError, match="varsayılan.*değerde"):
        enforce_security_startup(
            environment="production",
            gateway_security_enabled=True,
            gateway_secret=KNOWN_DEFAULT_SECRET,
            ticket_publisher="kafka",
        )


def test_production_with_disabled_gateway_security_raises():
    """Production ortamında gateway güvenlik kontrolü kapalıysa servis açılmamalıdır."""
    with pytest.raises(RuntimeError, match="GATEWAY_SECURITY_ENABLED=false"):
        enforce_security_startup(
            environment="production",
            gateway_security_enabled=False,
            gateway_secret="a" * 32,
            ticket_publisher="kafka",
        )


def test_production_with_short_secret_raises():
    """Production ortamında 32 karakterden kısa secret ile servis açılmamalıdır."""
    with pytest.raises(RuntimeError, match="32 karakterden kısa"):
        enforce_security_startup(
            environment="production",
            gateway_security_enabled=True,
            gateway_secret="short-secret-value",
            ticket_publisher="kafka",
        )


def test_production_with_logging_ticket_publisher_raises():
    """Production ortamında ticket publisher kafka değilse servis açılmamalıdır."""
    with pytest.raises(RuntimeError, match="TICKET_PUBLISHER=kafka değil"):
        enforce_security_startup(
            environment="production",
            gateway_security_enabled=True,
            gateway_secret="a" * 32,
            ticket_publisher="log",
        )


def test_production_with_strong_secret_and_kafka_passes():
    """Güçlü secret, devrede olan güvenlik ve kafka publisher ile production sorunsuz açılır."""
    enforce_security_startup(
        environment="production",
        gateway_security_enabled=True,
        gateway_secret="super-secure-production-secret-token-32plus",
        ticket_publisher="kafka",
    )


def test_error_message_never_contains_secret_value():
    """Hata mesajı hiçbir şekilde secret'ın kendisini içermemelidir."""
    secret_val = "kisa-gizli-bilgi"
    with pytest.raises(RuntimeError) as exc_info:
        enforce_security_startup(
            environment="production",
            gateway_security_enabled=True,
            gateway_secret=secret_val,
            ticket_publisher="kafka",
        )
    assert secret_val not in str(exc_info.value)


def test_environment_check_is_case_insensitive():
    """Ortam adı büyük/küçük harf duyarsız kontrol edilmelidir."""
    with pytest.raises(RuntimeError):
        enforce_security_startup(
            environment="PRODUCTION",
            gateway_security_enabled=True,
            gateway_secret=KNOWN_DEFAULT_SECRET,
            ticket_publisher="kafka",
        )

    # Dev ortamları fırlatmamalı
    for env in ("Development", "DEV", " Local ", "test"):
        enforce_security_startup(
            environment=env,
            gateway_security_enabled=True,
            gateway_secret=KNOWN_DEFAULT_SECRET,
            ticket_publisher="kafka",
        )


def test_default_settings_is_production_and_fails_fast_with_default_secret():
    """Varsayılan konfigürasyonda ENVIRONMENT=production ve DEBUG=False'dur; bilinen secret ile fail-fast çöker."""
    from app.core.config import Settings

    s = Settings(_env_file=None)
    assert s.ENVIRONMENT == "production"
    assert s.DEBUG is False
    with pytest.raises(RuntimeError, match="Güvensiz yapılandırma"):
        enforce_security_startup(
            environment=s.ENVIRONMENT,
            gateway_security_enabled=s.GATEWAY_SECURITY_ENABLED,
            gateway_secret=s.GATEWAY_INTERNAL_SECRET,
            ticket_publisher=s.TICKET_PUBLISHER,
        )
