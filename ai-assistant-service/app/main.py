"""FastAPI Ana Uygulama Modülü.

Bu modül, mikroservisin ana FastAPI uygulamasını, yaşam döngüsünü (lifespan)
ve HTTP yönlendirmelerini (router) yönetir.

Mimari Standart:
Lifespan (başlatma ve kapatma) karmaşıklaştığı için alt servis başlatıcıları
bağımsız fonksiyonlara ayrılmıştır (SRP - Single Responsibility Principle).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
from typing import Any, Callable

from fastapi import Depends, FastAPI
from qdrant_client import QdrantClient

from app.agent.executor import ActionExecutor
from app.agent.pending import InMemoryPendingActionStore, PendingActionStore
from app.agent.service import AgentService
from app.agent.tickets import KafkaTicketPublisher, LoggingTicketPublisher, TicketPublisher
from app.agent.tools.actions import RequestOrderCancellationTool, RequestSupportTicketTool
from app.agent.tools.orders import GetOrderTool, ListMyOrdersTool
from app.agent.tools.policy import SearchPolicyTool
from app.agent.tools.registry import ToolRegistry
from app.agent.tools.shipping import GetShipmentTool
from app.api.actuator import router as actuator_router
from app.api.api import api_router
from app.clients.order import OrderClient
from app.clients.shipping import ShippingClient
from app.core.config import settings
from app.core.errors import register_problem_details_handlers
from app.core.limits import BodySizeLimitMiddleware, ConcurrencyLimiter
from app.core.security import require_gateway_secret
from app.core.startup_checks import enforce_security_startup
from app.budget.service import TokenBudgetService
from app.budget.store import BudgetStore, InMemoryBudgetStore
from app.discovery.client import EurekaClient
from app.discovery.drain import install_sigterm_drain
from app.discovery.models import InstanceInfo
from app.discovery.network import resolve_instance_host
from app.discovery.registrar import EurekaRegistrar
from app.llm.factory import LLMFactory
from app.observability.context import RequestContextMiddleware
from app.observability.logging import configure_logging
from app.observability.metrics import HttpMetricsMiddleware
from app.observability.tracing import setup_tracing, shutdown_tracing
from app.rag.chunking.tokenizer import TiktokenTokenizer
from app.rag.embedding.base import Embedder
from app.rag.embedding.factory import get_default_embedder
from app.rag.generation.models import GenerationConfig
from app.rag.generation.service import RagAnswerService
from app.rag.rerank.factory import build_reranker_from_settings
from app.rag.vectorstore.models import QdrantConfig
from app.rag.vectorstore.store import QdrantStore
from app.runtimeconfig.client import ConfigServerClient
from app.runtimeconfig.holder import RuntimeConfigHolder
from app.runtimeconfig.listeners import apply_log_level
from app.runtimeconfig.loader import initial_load
from app.runtimeconfig.models import RuntimeSettings, pinned_paths

logger = logging.getLogger(__name__)

# Uygulama genelinde kurumsal loglama altyapısını başlat (stdout handler, JSON/PII formatlayıcı)
configure_logging()


# ============================================================================
# 0. RUNTIME KONFİGÜRASYON (CONFIG SERVER) KURULUMU
# ============================================================================

async def _init_runtime_config() -> tuple[RuntimeConfigHolder, ConfigServerClient | None]:
    """Başlangıçta Config Server'dan ayarları çeker ve holder'ı hazırlar.

    Mimari Kural:
    Bu fonksiyon lifespan'in en başında çağrılmalıdır. Instance henüz trafik
    almaya başlamadan önce çalışma zamanı konfigürasyonu kesinleşmiş olmalıdır.
    """
    baseline = RuntimeSettings.from_startup(settings)
    pinned = pinned_paths(settings)
    holder = RuntimeConfigHolder(baseline, pinned)

    # Log seviyesi dinleyicisini bağla ve baseline değerini uygula
    holder.add_listener(apply_log_level)
    apply_log_level(None, holder.current)

    if not settings.CONFIG_SERVER_ENABLED:
        return holder, None

    if pinned:
        logger.warning(
            "Env ile sabitlenmiş runtime alanları (Config Server yok sayacak): %s",
            ", ".join(sorted(pinned)),
        )

    client = ConfigServerClient(
        settings.CONFIG_SERVER_URL,
        timeout_sec=settings.CONFIG_REQUEST_TIMEOUT_SEC,
    )

    # Açılışta en fazla 3 kez bağlanmayı dene
    ok = await initial_load(
        holder,
        client,
        app_name=settings.SERVICE_NAME,
        profile=settings.CONFIG_PROFILE,
        attempts=settings.CONFIG_INITIAL_ATTEMPTS,
    )

    if not ok:
        if settings.CONFIG_FAIL_FAST:
            await client.aclose()
            raise RuntimeError(
                "Config Server'dan başlangıç konfigürasyonu alınamadı (CONFIG_FAIL_FAST=true)"
            )
        logger.warning(
            "Config Server'a ulaşılamadı; yerel/env runtime ayarlarıyla devam ediliyor."
        )

    return holder, client


# ============================================================================
# 1. VEKTÖR VERİTABANI VE EMBEDDING KURULUMU
# ============================================================================

def _init_vector_store() -> tuple[Embedder | None, QdrantClient | None, QdrantStore | None]:
    """Qdrant vektör veritabanını ve metin vektörleştirme (Embedding) motorunu başlatır.
    
    Ne İşe Yarar?
    - Embedder: Kullanıcının metinlerini veya PDF dokümanlarını çok boyutlu sayı dizilerine (vektör) çevirir.
    - QdrantStore: Bu vektörleri ve doküman parçalarını hafızada/disk üzerinde saklar ve anlamsal (semantik) arama yapar.
    """
    embedder: Embedder | None = None
    client: QdrantClient | None = None
    store: QdrantStore | None = None

    # 1. Adım: Vektörleştirici (Embedder) modelini yükle
    try:
        embedder = get_default_embedder()
    except Exception as exc:
        logger.warning("Varsayılan embedder başlatılamadı (API anahtarı eksik olabilir): %s", exc)

    # 2. Adım: Qdrant vektör veritabanı istemcisini oluştur
    try:
        config = QdrantConfig(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY or None,
            collection_prefix=settings.QDRANT_COLLECTION_PREFIX,
        )
        client = config.create_client()

        # Eğer hem istemci hem embedder hazırsa depolama katmanını (store) bağla
        if embedder is not None:
            store = QdrantStore(client=client, config=config, embedder=embedder)
    except Exception as exc:
        logger.warning("QdrantStore başlatılamadı: %s", exc)

    return embedder, client, store


# ============================================================================
# 2. RAG CEVAP ÜRETİM MOTORU KURULUMU (Retrieval-Augmented Generation)
# ============================================================================

def _init_rag_service(
    store: QdrantStore | None,
    embedder: Embedder | None,
) -> RagAnswerService | None:
    """Dokümanlara dayalı, halüsinasyonu engelleyen RAG cevaplama motorunu kurar.
    
    Bileşenler:
    - LLM: Cevap metnini üreten temel dil modeli (Gemini, OpenAI vb.).
    - Tokenizer: Metnin kaç token tuttuğunu hesaplayan sayaç (Tiktoken).
    - Reranker: Qdrant'tan gelen aday parçaları daha hassas bir çapraz kodlayıcıyla (Cross-Encoder) yeniden puanlayan model.
    """
    if store is None or embedder is None:
        logger.warning("Vektör deposu veya embedder eksik olduğundan RagAnswerService kurulamadı.")
        return None

    try:
        # LLM sağlayıcısını ayarlar dosyasından al (varsayılan: Gemini)
        provider_name = settings.RAG_LLM_PROVIDER or None
        model_name = settings.RAG_LLM_MODEL or None
        llm = LLMFactory.get_provider(provider_name, model_name=model_name)

        tokenizer = TiktokenTokenizer()
        gen_config = GenerationConfig.from_settings(settings)

        # Reranker modelini başlat ve ilk istekte gecikme yaşanmaması için ısıt (warmup)
        reranker = None
        try:
            reranker = build_reranker_from_settings(settings)
            if reranker is not None and hasattr(reranker, "warmup"):
                logger.info("Reranker modeli ısıtılıyor...")
                reranker.warmup()
        except Exception as exc:
            logger.warning("Reranker başlatılamadı veya ısıtılamadı (devre dışı bırakıldı): %s", exc)

        return RagAnswerService(
            store=store,
            embedder=embedder,
            llm=llm,
            tokenizer=tokenizer,
            config=gen_config,
            reranker=reranker,
        )
    except Exception as exc:
        logger.warning("RagAnswerService başlatılamadı: %s", exc)
        return None


# ============================================================================
# 3. DOWNSTREAM İSTEMCİLERİ VE EYLEM (ACTION) ALTYAPISI
# ============================================================================

def _init_downstream_and_actions() -> tuple[OrderClient, ShippingClient, PendingActionStore, TicketPublisher, ActionExecutor]:
    """Diğer mikroservislerle iletişim kuran HTTP istemcilerini ve eylem altyapısını başlatır.
    
    Ne İşe Yarar?
    - OrderClient: 'order-service' (port 8082) ile konuşarak sipariş bilgilerini çeker veya iptal eder.
    - ShippingClient: 'shipping-service' (port 8085) ile konuşarak kargo durumunu sorgular.
    - ActionStore: Hassas işlemler (sipariş iptali vb.) için kullanıcı onayını bekleyen eylemleri geçici saklar.
    - TicketPublisher: AI çözemediğinde insan desteğe aktarılacak destek biletlerini (Kafka/Log) yayınlar.
    - ActionExecutor: Kullanıcı aksiyonu onayladığında siparişi gerçekten iptal eden yürütücü.
    """
    order_client = OrderClient(
        base_url=settings.ORDER_SERVICE_URL,
        timeout_sec=settings.DOWNSTREAM_TIMEOUT_SEC,
    )
    shipping_client = ShippingClient(
        base_url=settings.SHIPPING_SERVICE_URL,
        timeout_sec=settings.DOWNSTREAM_TIMEOUT_SEC,
    )

    action_store: PendingActionStore
    if settings.REDIS_ENABLED:
        try:
            import redis
            from app.agent.redis_pending import RedisPendingActionStore
            sync_redis = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD or None,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
            )
            action_store = RedisPendingActionStore(sync_redis)
            from app.core.audit import RedisDenyTracker, set_deny_tracker
            set_deny_tracker(
                RedisDenyTracker(
                    sync_redis,
                    threshold=settings.AUDIT_DENY_THRESHOLD,
                    window_sec=settings.AUDIT_DENY_WINDOW_SEC,
                )
            )
            logger.info("RedisPendingActionStore ve RedisDenyTracker başlatıldı (%s:%d)", settings.REDIS_HOST, settings.REDIS_PORT)
        except Exception as exc:
            logger.warning("RedisPendingActionStore başlatılamadı, InMemory depoya geçiliyor: %s", exc)
            action_store = InMemoryPendingActionStore()
    else:
        logger.warning("REDIS_ENABLED=False olduğundan InMemoryPendingActionStore kullanılıyor (birden fazla replikada confirm çalışmaz).")
        action_store = InMemoryPendingActionStore()

    # Destek biletleri ortam ayarına göre Kafka'ya veya doğrudan log konsoluna yazılır
    if settings.TICKET_PUBLISHER == "kafka":
        ticket_publisher: TicketPublisher = KafkaTicketPublisher()
    else:
        ticket_publisher = LoggingTicketPublisher()

    action_executor = ActionExecutor(
        order_client=order_client,
        ticket_publisher=ticket_publisher,
    )

    return order_client, shipping_client, action_store, ticket_publisher, action_executor


# ============================================================================
# 4. AI MÜŞTERİ HİZMETLERİ AGENT VE ARAÇLAR (TOOLS) KURULUMU
# ============================================================================

def _init_agent_service(
    rag_service: RagAnswerService | None,
    order_client: OrderClient,
    shipping_client: ShippingClient,
    action_store: PendingActionStore,
) -> AgentService | None:
    """Kullanıcıyla sohbet eden, sipariş sorgulayan ve araçları yöneten otonom Ajanı kurar.
    
    Ne İşe Yarar?
    - ToolRegistry: Ajanın kullanabileceği tüm araçların (fonksiyonların) kayıt defteridir.
      1. SearchPolicyTool: Şirket iade/garanti politikalarını RAG üzerinden arar.
      2. GetOrderTool / ListMyOrdersTool: Müşterinin sipariş detaylarını çeker.
      3. GetShipmentTool: Kargo takip durumunu getirir.
      4. RequestOrderCancellationTool: Sipariş iptali için onay kartı üretir.
      5. RequestSupportTicketTool: Çözülemeyen sorunlar için destek kaydı oluşturur.
    """
    try:
        agent_provider = settings.AGENT_LLM_PROVIDER or None
        agent_model = settings.AGENT_LLM_MODEL or None
        agent_llm = LLMFactory.get_provider(agent_provider, model_name=agent_model)

        registry = ToolRegistry()

        # Politika arama aracı yalnızca RAG servisi ayaktaysa ajana sunulur
        if rag_service is not None:
            registry.register(SearchPolicyTool(rag_service))
        else:
            logger.warning("RagAnswerService mevcut olmadığı için SearchPolicyTool kaydedilmedi.")

        # Sipariş ve kargo araçlarını deftere kaydet
        registry.register(GetOrderTool(order_client))
        registry.register(ListMyOrdersTool(order_client))
        registry.register(GetShipmentTool(order_client, shipping_client))

        # Hassas onay gerektiren eylem araçlarını kaydet (Human-in-the-Loop)
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

        return AgentService(llm=agent_llm, registry=registry)
    except Exception as exc:
        logger.warning("AgentService başlatılamadı: %s", exc)
        return None


# ============================================================================
# 5. TOKEN BÜTÇESİ SERVİSİ KURULUMU
# ============================================================================

def _init_token_budget() -> tuple[TokenBudgetService | None, Any | None]:
    """Token bütçesi ve maliyet koruma servisini (RedisBudgetStore + Fallback) başlatır.
    
    Ne İşe Yarar?
    - Kullanıcı ve sistem bazında token kullanımını günlük ve dakikalık limitlerle sınırlar.
    - REDIS_ENABLED=True ise çoklu replikalar için RedisBudgetStore kurar; arıza durumunda InMemory depoya döner.
    """
    if not settings.TOKEN_BUDGET_ENABLED:
        return None, None

    fallback_store = InMemoryBudgetStore()
    redis_client = None
    store: BudgetStore = fallback_store

    if settings.REDIS_ENABLED:
        try:
            from redis.asyncio import Redis
            from app.budget.redis_store import RedisBudgetStore

            redis_client = Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD or None,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
            )
            store = RedisBudgetStore(redis_client)
            logger.info("TokenBudgetService Redis bağlantısıyla başlatıldı (%s:%d)", settings.REDIS_HOST, settings.REDIS_PORT)
        except Exception as exc:
            logger.warning("Redis bütçe deposu başlatılamadı, yerel InMemory depoya geçiliyor: %s", exc)
            store = fallback_store
    else:
        logger.warning("REDIS_ENABLED=False olduğundan TokenBudgetService yalnızca InMemory çalışıyor.")

    service = TokenBudgetService(
        store=store,
        fallback_store=fallback_store,
        daily_limit=settings.TOKEN_BUDGET_DAILY_LIMIT,
        per_minute_limit=settings.TOKEN_BUDGET_PER_MINUTE_LIMIT,
        provider_tpm_limit=settings.PROVIDER_TPM_LIMIT,
        provider_name="default",
        fail_mode=settings.TOKEN_BUDGET_FAIL_MODE,
    )

    base_chat_estimate = (
        settings.TOKEN_BUDGET_PROMPT_OVERHEAD + settings.AGENT_MAX_OUTPUT_TOKENS
    ) * min(2, max(1, settings.AGENT_MAX_STEPS))
    if base_chat_estimate > settings.TOKEN_BUDGET_PER_MINUTE_LIMIT:
        logger.warning(
            "YAPILANDIRMA UYARISI: Tahmini tekil sohbet bütçesi (%d token), "
            "dakikalık kullanıcı kotasından (%d token) büyük! Sohbet istekleri 429 alabilir.",
            base_chat_estimate,
            settings.TOKEN_BUDGET_PER_MINUTE_LIMIT,
        )

    return service, redis_client


# ============================================================================
# 6. EUREKA SERVICE DISCOVERY VE GRACEFUL DRAIN KURULUMU
# ============================================================================

async def _init_eureka() -> tuple[EurekaRegistrar | None, Callable[[], None] | None]:
    """Eureka Service Registry kaydını ve SIGTERM anında graceful drain mekanizmasını kurar.
    
    Ne İşe Yarar?
    - EurekaRegistrar: Servisi Spring Cloud Eureka'ya kaydeder ('AI-ASSISTANT-SERVICE') ve 10 saniyede bir heartbeat atar.
    - install_sigterm_drain: Container kapatılırken (SIGTERM), önce Eureka'dan kaydı siler ve 20s bekler.
      Böylece API Gateway önbelleğindeki eski adrese istek gönderip hata almayı (kesintiyi) önler.
    """
    if not settings.EUREKA_ENABLED:
        return None, None

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
        logger.info("Eureka registrar başarıyla başlatıldı (instance_id: %s)", instance_id)
        return eureka_registrar, sigterm_restore
    except Exception as exc:
        logger.warning("Eureka registrar başlatılamadı (uygulama devam ediyor): %s", exc)
        return None, None


# ============================================================================
# 6. SHUTDOWN KAYNAK TEMİZLEME YÖNETİCİSİ
# ============================================================================

async def _cleanup_resources(
    sigterm_restore: Callable[[], None] | None,
    eureka_registrar: EurekaRegistrar | None,
    order_client: OrderClient | None,
    shipping_client: ShippingClient | None,
    ticket_publisher: TicketPublisher | None,
    client: QdrantClient | None,
    redis_client: Any | None = None,
    config_server_client: ConfigServerClient | None = None,
) -> None:
    """Uygulama kapanırken açık ağ bağlantılarını ve thread'leri güvenle serbest bırakır."""
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

    if config_server_client is not None:
        try:
            await config_server_client.aclose()
        except Exception as exc:
            logger.warning("ConfigServerClient kapatılırken hata: %s", exc)

    if redis_client is not None:
        try:
            await redis_client.aclose()
        except Exception as exc:
            logger.warning("Redis istemcisi kapatılırken hata: %s", exc)

    if order_client and hasattr(order_client, "close"):
        try:
            await order_client.close()
        except Exception as exc:
            logger.warning("OrderClient kapatılırken hata: %s", exc)

    if shipping_client and hasattr(shipping_client, "close"):
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


# ============================================================================
# 7. FASTAPI LIFESPAN ORKESTRASYONU
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI Uygulama Yaşam Döngüsü Yöneticisi (Startup & Shutdown).
    
    Tüm alt bileşenleri sıralı ve kontrollü bir şekilde başlatıp `app.state`'e ekler.
    Uygulama kapatıldığında (Ctrl+C veya SIGTERM) açık soketleri ve bağlantıları temizler.
    """
    # -1. Adım: Başlangıç Güvenlik Denetimi (Startup Security Checks)
    # Üretim (production) ortamında varsayılan zayıf secret veya kapalı çevre güvenliği varsa
    # servisin çalışmasına izin verilmez (Fail-Fast prensibiyle uygulama burada anında durdurulur).
    enforce_security_startup(
        environment=settings.ENVIRONMENT,
        gateway_security_enabled=settings.GATEWAY_SECURITY_ENABLED,
        gateway_secret=settings.GATEWAY_INTERNAL_SECRET,
        ticket_publisher=settings.TICKET_PUBLISHER,
    )

    # 0. Adım: Runtime Konfigürasyon (Config Server) Başlatma
    runtime_config, config_client = await _init_runtime_config()

    # 1. Adım: Vektör Veritabanı ve Embedding modellerini ayağa kaldır
    embedder, client, store = _init_vector_store()

    # 2. Adım: Doküman tabanlı RAG motorunu başlat
    rag_answer_service = _init_rag_service(store=store, embedder=embedder)

    # 3. Adım: Sipariş, Kargo ve Aksiyon istemcilerini kur
    (
        order_client,
        shipping_client,
        action_store,
        ticket_publisher,
        action_executor,
    ) = _init_downstream_and_actions()

    # 4. Adım: Müşteri Temsilcisi AI Ajanını ve Araçlarını kur
    agent_service = _init_agent_service(
        rag_service=rag_answer_service,
        order_client=order_client,
        shipping_client=shipping_client,
        action_store=action_store,
    )

    # 5. Adım: Eşzamanlılık Denetleyicisi (Süreç başına en fazla 20 aktif LLM işlemi)
    ai_limiter = ConcurrencyLimiter(max_concurrent=settings.AI_MAX_CONCURRENT_REQUESTS)

    # 6. Adım: Token Bütçesi ve Maliyet Koruması (Kullanıcı ve Provider kotaları)
    token_budget, redis_client = _init_token_budget()

    # Tüm servis referanslarını FastAPI endpoint'lerinin erişebilmesi için app.state'e kaydet
    app.state.runtime_config = runtime_config
    app.state.config_server_client = config_client
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
    app.state.ai_limiter = ai_limiter
    app.state.token_budget = token_budget
    app.state.redis_client = redis_client

    # 7. Adım: Servis Keşfi (Eureka) ve Graceful Drain mekanizmasını başlat
    eureka_registrar, sigterm_restore = await _init_eureka()
    app.state.eureka_registrar = eureka_registrar

    # --- UYGULAMA ÇALIŞIYOR (İstekler kabul edilir) ---
    yield

    # --- UYGULAMA KAPANIYOR (Shutdown temizliği) ---
    await _cleanup_resources(
        sigterm_restore=sigterm_restore,
        eureka_registrar=eureka_registrar,
        order_client=order_client,
        shipping_client=shipping_client,
        ticket_publisher=ticket_publisher,
        client=client,
        redis_client=redis_client,
        config_server_client=config_client,
    )
    # Açık span tamponunu boşalt ve trace sağlayıcısını güvenle kapat
    shutdown_tracing(tracing_provider)


# ============================================================================
# 8. FASTAPI UYGULAMA TANIMI VE MIDDLEWARE KAYITLARI
# ============================================================================

app = FastAPI(
    title=settings.SERVICE_NAME,
    version="0.1.0",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# OpenTelemetry Dağıtık İzleme (Tracing) kurulumu ve FastAPI/HTTPX enstrümantasyonu
tracing_provider = setup_tracing(app)

# İstek gövdesi koruması: 64 KB üzerindeki POST isteklerini belleğe almadan 413 Payload Too Large ile reddet
app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.AI_MAX_BODY_BYTES)

# Dağıtık izleme bağlamı: X-Correlation-Id başlığını temizleyip ContextVar'a kaydet
app.add_middleware(RequestContextMiddleware)

# Prometheus HTTP İstek Metrikleri: Süre, route şablonu, durum kodu ve sonuç dağılımını ölç
app.add_middleware(HttpMetricsMiddleware)

# RFC 7807 standart ProblemDetails hata yakalayıcılarını kaydet
register_problem_details_handlers(app)

# Ana API yönlendiricisini (Router) dahil et (/agent, /api/v1/chat, /rag)
app.include_router(api_router)
# Actuator canlı konfigürasyon yenileme yönlendiricisi (/actuator/refresh).
# Güvenlik Kuralı: Doğrudan dış ağdan veya yetkisiz çağrılmasını engellemek amacıyla
# 'require_gateway_secret' bağımlılığıyla korunur (geçerli X-Gateway-Secret başlığı zorunludur).
# Not: Aşağıdaki /health endpoint'i Docker/Kubernetes sağlık kontrolleri için kimliksiz (unauthenticated) 200 döner.
app.include_router(actuator_router, dependencies=[Depends(require_gateway_secret)])


@app.get("/health")
async def health_check():
    """Kubernetes veya Eureka için kimlik doğrulamasız sağlık kontrolü endpoint'i."""
    res: dict[str, Any] = {
        "status": "UP",
        "service": settings.SERVICE_NAME,
        "environment": settings.ENVIRONMENT,
    }
    holder = getattr(app.state, "runtime_config", None)
    if holder is not None:
        status = holder.status
        now = datetime.now(timezone.utc)
        last_success_age_sec = (
            int((now - status.last_success_at).total_seconds())
            if status.last_success_at is not None
            else None
        )
        res["config"] = {
            "source": status.source,
            "version": status.version,
            "last_success_age_sec": last_success_age_sec,
            "consecutive_failures": status.consecutive_failures,
            "last_error": status.last_error,
            "pinned": list(status.pinned),
        }
    return res
