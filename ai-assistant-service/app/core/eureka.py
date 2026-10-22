import logging

from py_eureka_client import eureka_client

from app.core.config import settings

logger = logging.getLogger(__name__)


class EurekaLifecycleManager:
    """Manages registration and deregistration of ai-assistant-service with Spring Cloud Netflix Eureka."""

    def __init__(self) -> None:
        self._registered = False

    async def start(self) -> None:
        if not settings.EUREKA_ENABLED:
            logger.info("Eureka registration is disabled via configuration (EUREKA_ENABLED=false).")
            return

        try:
            instance_id = f"{settings.SERVICE_NAME}:{settings.SERVICE_PORT}"
            await eureka_client.init_async(
                eureka_server=settings.EUREKA_SERVER_URL,
                app_name=settings.SERVICE_NAME,
                instance_id=instance_id,
                instance_host=settings.SERVICE_HOST,
                instance_port=settings.SERVICE_PORT,
                status_page_url=f"http://{settings.SERVICE_HOST}:{settings.SERVICE_PORT}/actuator/info",
                health_check_url=f"http://{settings.SERVICE_HOST}:{settings.SERVICE_PORT}/actuator/health",
            )
            self._registered = True
            logger.info(
                "Registered %s (%s) with Eureka Server at %s",
                settings.SERVICE_NAME,
                instance_id,
                settings.EUREKA_SERVER_URL,
            )
        except Exception as exc:
            logger.error("Failed to register with Eureka Server: %s", exc)

    async def stop(self) -> None:
        if self._registered:
            try:
                await eureka_client.stop_async()
                logger.info("Deregistered %s from Eureka Server.", settings.SERVICE_NAME)
            except Exception as exc:
                logger.warning("Error while stopping Eureka client: %s", exc)
            finally:
                self._registered = False


eureka_manager = EurekaLifecycleManager()
