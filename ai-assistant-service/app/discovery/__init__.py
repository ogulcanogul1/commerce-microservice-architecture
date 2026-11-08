"""Eureka Service Discovery paketi."""

from app.discovery.client import EurekaClient, EurekaError
from app.discovery.drain import install_sigterm_drain
from app.discovery.models import InstanceInfo
from app.discovery.network import resolve_instance_host
from app.discovery.registrar import EurekaRegistrar

__all__ = [
    "EurekaClient",
    "EurekaError",
    "EurekaRegistrar",
    "InstanceInfo",
    "install_sigterm_drain",
    "resolve_instance_host",
]
