"""FastAPI Ana Uygulama Modülü.

Bu modül, mikroservisin ana FastAPI uygulamasını, yaşam döngüsünü (lifespan)
ve HTTP yönlendirmelerini (router) yönetir.
"""

from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from qdrant_client import QdrantClient

from app.agent.executor import ActionExecutor
from app.agent.pending import InMemoryPendingActionStore
from app.agent.service import AgentService
from app.agent.tickets import KafkaTicketPublisher, LoggingTicketPublisher, TicketPublisher
from app.agent.tools.actions import RequestOrderCancellationTool, RequestSupportTicketTool
from app.agent.tools.orders import GetOrderTool, ListMyOrdersTool
from app.agent.tools.policy import SearchPolicyTool
from app.agent.tools.registry import ToolRegistry
from app.agent.tools.shipping import GetShipmentTool
from app.api.api import api_router
from app.clients.order import OrderClient
from app.clients.shipping import ShippingClient
from app.core.config import settings
from app.core.errors import register_problem_details_handlers
from app.discovery.client import EurekaClient
from app.discovery.drain import install_sigterm_drain
from app.discovery.models import InstanceInfo
from app.discovery.network import resolve_instance_host
from app.discovery.registrar import EurekaRegistrar
from app.llm.factory import LLMFactory
from app.rag.chunking.tokenizer import TiktokenTokenizer
from app.rag.embedding.factory import get_default_embedder
from app.rag.generation.models import GenerationConfig
from app.rag.generation.service import RagAnswerService
from app.rag.rerank.factory import build_reranker_from_settings
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
        reranker = None
        try:
            reranker = build_reranker_from_settings(settings)
            if reranker is not None and hasattr(reranker, "warmup"):
                logger.info("Reranker modeli ısıtılıyor...")
                reranker.warmup()
        except Exception as exc:
            logger.warning("Reranker başlatılamadı veya ısıtılamadı (devre dışı bırakıldı): %s", exc)

        if store is not None and embedder is not None:
            rag_answer_service = RagAnswerService(
                store=store,
                embedder=embedder,
                llm=llm,
                tokenizer=tokenizer,
                config=gen_config,
                reranker=reranker,
            )
    except Exception as exc:
        logger.warning("RagAnswerService başlatılamadı: %s", exc)

    # Downstream Clients & Action Infrastructure
    order_client = OrderClient(
        base_url=settings.ORDER_SERVICE_URL,
        timeout_sec=settings.DOWNSTREAM_TIMEOUT_SEC,
    )
    shipping_client = ShippingClient(
        base_url=settings.SHIPPING_SERVICE_URL,
        timeout_sec=settings.DOWNSTREAM_TIMEOUT_SEC,
    )
    action_store = InMemoryPendingActionStore()

    ticket_publisher: TicketPublisher
    if settings.TICKET_PUBLISHER == "kafka":
        ticket_publisher = KafkaTicketPublisher()
    else:
        ticket_publisher = LoggingTicketPublisher()

    action_executor = ActionExecutor(
        order_client=order_client,
        ticket_publisher=ticket_publisher,
    )

    # Customer Support Agent Service
    agent_service = None
    try:
        agent_provider = settings.AGENT_LLM_PROVIDER or None
        agent_model = settings.AGENT_LLM_MODEL or None
        agent_llm = LLMFactory.get_provider(agent_provider, model_name=agent_model)

        registry = ToolRegistry()
        if rag_answer_service is not None:
            registry.register(SearchPolicyTool(rag_answer_service))
        else:
            logger.warning(
                "RagAnswerService mevcut olmadığı için SearchPolicyTool kaydedilmedi."
            )

        registry.register(GetOrderTool(order_client))
        registry.register(ListMyOrdersTool(order_client))
        registry.register(GetShipmentTool(order_client, shipping_client))
        registry.register(
            RequestOrderCancellationTool(
                order_client,
                action_store,
                ttl_sec=settings.AGENT_PENDING_TTL_SEC,
            )
        )
        registry.register(
            RequestSupportTicketTool(
                order_client,
                action_store,
                ttl_sec=settings.AGENT_PENDING_TTL_SEC,
            )
        )

        agent_service = AgentService(llm=agent_llm, registry=registry)
    except Exception as exc:
        logger.warning("AgentService başlatılamadı: %s", exc)

    app.state.embedder = embedder
    app.state.qdrant_client = client
    app.state.qdrant_store = store
    app.state.rag_answer_service = rag_answer_service
    app.state.order_client = order_client
    app.state.shipping_client = shipping_client
    app.state.action_store = action_store
    app.state.action_executor = action_executor
    app.state.ticket_publisher = ticket_publisher
    app.state.agent_service = agent_service

    # Eureka Service Discovery Entegrasyonu (varsayılan: EUREKA_ENABLED=False)
    eureka_registrar = None
    sigterm_restore = None
    if settings.EUREKA_ENABLED:
        try:
            host, ip = resolve_instance_host(
                configured_host=settings.SERVICE_HOST,
                prefer_ip=settings.EUREKA_PREFER_IP,
            )
            service_slug = settings.SERVICE_NAME.lower().replace("_", "-")
            instance_id = f"{host}:{service_slug}:{settings.PORT}"
            health_url = f"http://{host}:{settings.PORT}/health"

            instance_info = InstanceInfo(
                app_name=settings.SERVICE_NAME.upper(),
                instance_id=instance_id,
                host=host,
                ip_addr=ip,
                port=settings.PORT,
                health_url=health_url,
                renewal_sec=settings.EUREKA_RENEWAL_SEC,
                lease_sec=settings.EUREKA_LEASE_SEC,
            )

            eureka_client = EurekaClient(
                base_url=settings.EUREKA_SERVER_URL,
                timeout_sec=settings.EUREKA_REQUEST_TIMEOUT_SEC,
            )

            eureka_registrar = EurekaRegistrar(
                client=eureka_client,
                info=instance_info,
                renewal_sec=settings.EUREKA_RENEWAL_SEC,
                drain_sec=settings.EUREKA_DRAIN_SEC,
            )

            await eureka_registrar.start()
            sigterm_restore = install_sigterm_drain(
                registrar=eureka_registrar,
                drain_sec=settings.EUREKA_DRAIN_SEC,
            )
            logger.info("Eureka registrar basariyla baslatildi (instance_id: %s)", instance_id)
        except Exception as exc:
            logger.warning("Eureka registrar baslatilamadi (uygulama devam ediyor): %s", exc)

    app.state.eureka_registrar = eureka_registrar

    yield

    # Shutdown
    if sigterm_restore is not None:
        try:
            sigterm_restore()
        except Exception:
            pass

    if eureka_registrar is not None:
        try:
            await eureka_registrar.stop()
        except Exception as exc:
            logger.warning("Eureka registrar kapatılırken hata: %s", exc)

    if hasattr(order_client, "close"):
        try:
            await order_client.close()
        except Exception as exc:
            logger.warning("OrderClient kapatılırken hata: %s", exc)

    if hasattr(shipping_client, "close"):
        try:
            await shipping_client.close()
        except Exception as exc:
            logger.warning("ShippingClient kapatılırken hata: %s", exc)

    if isinstance(ticket_publisher, KafkaTicketPublisher):
        try:
            await ticket_publisher.stop()
        except Exception as exc:
            logger.warning("KafkaTicketPublisher kapatılırken hata: %s", exc)

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
