"""API Router tanımlamaları.

Tüm servis alt uç noktaları bu ana router altında toplanır.
"""

from fastapi import APIRouter
from app.api.answer import router as answer_router
from app.api.search import router as search_router

api_router = APIRouter()
api_router.include_router(search_router)
api_router.include_router(answer_router)
