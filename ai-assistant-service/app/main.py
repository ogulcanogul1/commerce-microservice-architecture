from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI

from app.api.v1.health_controller import health_router
from app.core.config import settings
from app.core.eureka import eureka_manager
from app.core.exceptions import register_exception_handlers
from app.core.security import GatewaySecurityMiddleware
from app.core.telemetry import setup_telemetry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await eureka_manager.start()
    try:
        yield
    finally:
        await eureka_manager.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Commerce AI Assistant Service",
        description="Polyglot Agentic LLM Service for Order, Shipping, Price & Support Operations",
        version="0.1.0",
        openapi_url="/v3/api-docs",
        lifespan=lifespan,
    )

    app.add_middleware(GatewaySecurityMiddleware)
    register_exception_handlers(app)
    setup_telemetry(app)

    app.include_router(health_router)
    return app


app = create_app()
