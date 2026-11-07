"""Pytest root configuration and global fixtures for ai-assistant-service."""

from collections.abc import Generator
import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def disable_gateway_security_for_tests() -> Generator[None, None, None]:
    """Disable gateway secret validation by default for general unit/api tests.

    Security-specific tests in tests/core/test_security.py and tests/api/test_agent.py
    can explicitly enable it or supply valid headers.
    """
    original_state = settings.GATEWAY_SECURITY_ENABLED
    settings.GATEWAY_SECURITY_ENABLED = False
    try:
        yield
    finally:
        settings.GATEWAY_SECURITY_ENABLED = original_state
