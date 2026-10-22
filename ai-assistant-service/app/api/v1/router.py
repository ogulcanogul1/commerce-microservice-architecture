from fastapi import APIRouter

from app.api.v1.chat_controller import chat_router
from app.api.v1.health_controller import health_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(chat_router)
