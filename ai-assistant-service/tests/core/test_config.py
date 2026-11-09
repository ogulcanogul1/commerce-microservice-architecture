import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings


def test_config_server_default_settings() -> None:
    """Config Server için tanımlanan başlangıç ayarlarının varsayılan değerlerini doğrular."""
    assert settings.CONFIG_SERVER_ENABLED is False
    assert settings.CONFIG_SERVER_URL == "http://localhost:8888/"
    assert settings.CONFIG_PROFILE == "dev"
    assert settings.CONFIG_REQUEST_TIMEOUT_SEC == 3.0
    assert settings.CONFIG_INITIAL_ATTEMPTS == 3
    assert settings.CONFIG_FAIL_FAST is False


def test_config_server_profile_validation() -> None:
    """CONFIG_PROFILE yalnızca dev, qa, prod, default, test değerlerini alabilir."""
    # Geçerli profiller
    for profile in ["dev", "qa", "prod", "default", "test"]:
        s = Settings(_env_file=None, CONFIG_PROFILE=profile)
        assert s.CONFIG_PROFILE == profile

    # Geçersiz profil adı
    with pytest.raises(ValidationError):
        Settings(_env_file=None, CONFIG_PROFILE="invalid_profile")


def test_config_server_initial_attempts_validation() -> None:
    """CONFIG_INITIAL_ATTEMPTS 1 ile 10 arasında olmalıdır."""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, CONFIG_INITIAL_ATTEMPTS=0)

    with pytest.raises(ValidationError):
        Settings(_env_file=None, CONFIG_INITIAL_ATTEMPTS=11)



def test_audit_deny_threshold_validation() -> None:
    """AUDIT_DENY_THRESHOLD en az 1 olmalıdır; 0 veya negatif değerler ValidationError fırlatır."""
    s = Settings(_env_file=None, AUDIT_DENY_THRESHOLD=5)
    assert s.AUDIT_DENY_THRESHOLD == 5

    with pytest.raises(ValidationError):
        Settings(_env_file=None, AUDIT_DENY_THRESHOLD=0)

    with pytest.raises(ValidationError):
        Settings(_env_file=None, AUDIT_DENY_THRESHOLD=-1)
