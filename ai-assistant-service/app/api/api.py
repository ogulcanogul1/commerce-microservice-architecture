"""API Router tanımlamaları.

Tüm servis alt uç noktaları bu ana router altında toplanır.
"""

from fastapi import APIRouter
from app.api.search import router as search_router

api_router = APIRouter()
api_router.include_router(search_router)
