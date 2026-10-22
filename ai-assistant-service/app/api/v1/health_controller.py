from fastapi import APIRouter

health_router = APIRouter(tags=["Health & Actuator"])


@health_router.get("/actuator/health")
async def actuator_health() -> dict:
    return {
        "status": "UP",
        "components": {
            "aiAssistant": {"status": "UP"},
        },
    }


@health_router.get("/actuator/info")
async def actuator_info() -> dict:
    return {
        "app": {
            "name": "ai-assistant-service",
            "version": "0.1.0",
            "runtime": "Python 3.12 / FastAPI (uv)",
        }
    }
