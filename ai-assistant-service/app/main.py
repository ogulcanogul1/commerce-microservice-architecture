"""FastAPI Ana Uygulama Modülü.

Bu modül, mikroservisin ana FastAPI uygulamasını, yaşam döngüsünü (lifespan)
ve HTTP yönlendirmelerini (router) yönetir.
"""

from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from qdrant_client import QdrantClient

from app.api.api import api_router
from app.core.config import settings
from app.rag.embedding.factory import get_default_embedder
from app.rag.vectorstore.models import QdrantConfig
from app.rag.vectorstore.store import QdrantStore

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Uygulama yaşam döngüsü yöneticisi (Startup & Shutdown).

    Qdrant istemcisi, store ve embedder nesneleri import anında değil,
    uygulama ayağa kalkarken (startup) oluşturulur ve app.state'e eklenir.
    Uygulama kapanırken açık bağlantılar temizlenir.
    """
    embedder = None
    client = None
    store = None

    try:
        embedder = get_default_embedder()
    except Exception as exc:
        logger.warning("Varsayılan embedder başlatılamadı (API anahtarı eksik olabilir): %s", exc)

    try:
        client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY or None,
            timeout=30.0,
        )
        config = QdrantConfig(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY or None,
            collection_prefix=settings.QDRANT_COLLECTION_PREFIX,
        )
        if embedder is not None:
            store = QdrantStore(client=client, config=config, embedder=embedder)
    except Exception as exc:
        logger.warning("QdrantStore başlatılamadı: %s", exc)

    app.state.embedder = embedder
    app.state.qdrant_client = client
    app.state.qdrant_store = store

    yield

    # Shutdown
    if client is not None:
        try:
            client.close()
        except Exception as exc:
            logger.warning("QdrantClient kapatılırken hata: %s", exc)


app = FastAPI(
    title=settings.SERVICE_NAME,
    version="0.1.0",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

app.include_router(api_router)


@app.get("/health")
async def health_check():
    return {
        "status": "UP",
        "service": settings.SERVICE_NAME,
        "environment": settings.ENVIRONMENT,
    }
