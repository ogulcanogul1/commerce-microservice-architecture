"""Runtime dinleyicileri (apply_log_level) birim testleri."""

import logging
from unittest.mock import patch
import pytest

from app.core.config import Settings
from app.runtimeconfig.listeners import apply_log_level
from app.runtimeconfig.models import LoggingRuntime, RuntimeSettings


@pytest.fixture
def base_rt() -> RuntimeSettings:
    return RuntimeSettings.from_startup(Settings(_env_file=None))


def test_apply_log_level_startup_and_dynamic_change(base_rt: RuntimeSettings) -> None:
    """Log seviyesinin açılışta ve dinamik değişimde doğru ayarlandığını doğrular."""
    app_logger = logging.getLogger("app")
    original_level = app_logger.level

    try:
        # 1. Başlangıç (old=None, level=None) -> NOTSET olmalı
        apply_log_level(None, base_rt)
        assert app_logger.level == logging.NOTSET

        # 2. DEBUG seviyesine değişim
        rt_debug = base_rt.model_copy(update={"logging": LoggingRuntime(level="DEBUG")})
        apply_log_level(base_rt, rt_debug)
        assert app_logger.level == logging.DEBUG

        # 3. WARNING seviyesine değişim
        rt_warn = base_rt.model_copy(update={"logging": LoggingRuntime(level="WARNING")})
        apply_log_level(rt_debug, rt_warn)
        assert app_logger.level == logging.WARNING

        # 4. Aynı seviye geldiğinde setLevel çağrılmamalı
        with patch.object(app_logger, "setLevel") as mock_set:
            apply_log_level(rt_warn, rt_warn)
            mock_set.assert_not_called()

        # 5. Tekrar None yapıldığında NOTSET olmalı
        apply_log_level(rt_warn, base_rt)
        assert app_logger.level == logging.NOTSET
    finally:
        app_logger.setLevel(original_level)
