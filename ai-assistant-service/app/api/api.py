"""API Router tanımlamaları.

Tüm servis alt uç noktaları bu ana router altında toplanır.
"""

from fastapi import APIRouter, Depends
from app.api.agent import router as agent_router
from app.api.answer import router as answer_router
from app.api.search import router as search_router
from app.core.security import require_gateway_secret

# Tüm alt router'lara Gateway Secret kontrolünü zorunlu kılan ana API router'ı (doğrudan port erişimini engeller)
api_router = APIRouter(dependencies=[Depends(require_gateway_secret)])
# Doküman semantik arama rotasını ekler (POST /rag/search uç noktası)
api_router.include_router(search_router)
# Doküman kaynaklı soru yanıtlama rotasını ekler (POST /rag/answer uç noktası)
api_router.include_router(answer_router)
# Müşteri destek ajanı ve onaylı aksiyon rotalarını ekler (hem /agent hem /api/v1/chat rotalarını destekler)
api_router.include_router(agent_router, prefix="/agent", tags=["Agent"])
api_router.include_router(agent_router, prefix="/api/v1/chat", tags=["Agent Chat"])
