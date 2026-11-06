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
from app.core.errors import register_problem_details_handlers
from app.llm.factory import LLMFactory
from app.rag.chunking.tokenizer import TiktokenTokenizer
from app.rag.embedding.factory import get_default_embedder
from app.rag.generation.models import GenerationConfig
from app.rag.generation.service import RagAnswerService
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
        config = QdrantConfig(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY or None,
            collection_prefix=settings.QDRANT_COLLECTION_PREFIX,
        )
        client = config.create_client()
        if embedder is not None:
            store = QdrantStore(client=client, config=config, embedder=embedder)
    except Exception as exc:
        logger.warning("QdrantStore başlatılamadı: %s", exc)

    rag_answer_service = None
    try:
        provider_name = settings.RAG_LLM_PROVIDER or None
        model_name = settings.RAG_LLM_MODEL or None
        llm = LLMFactory.get_provider(provider_name, model_name=model_name)
        tokenizer = TiktokenTokenizer()
        gen_config = GenerationConfig.from_settings(settings)
        if store is not None and embedder is not None:
            rag_answer_service = RagAnswerService(
                store=store,
                embedder=embedder,
                llm=llm,
                tokenizer=tokenizer,
                config=gen_config,
            )
    except Exception as exc:
        logger.warning("RagAnswerService başlatılamadı: %s", exc)

    app.state.embedder = embedder
    app.state.qdrant_client = client
    app.state.qdrant_store = store
    app.state.rag_answer_service = rag_answer_service

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

register_problem_details_handlers(app)
app.include_router(api_router)


@app.get("/health")
async def health_check():
    return {
        "status": "UP",
        "service": settings.SERVICE_NAME,
        "environment": settings.ENVIRONMENT,
    }
