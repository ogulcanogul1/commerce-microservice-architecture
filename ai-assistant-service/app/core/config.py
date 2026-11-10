from functools import lru_cache
from typing import Any, Literal
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Service Info
    SERVICE_NAME: str = "ai-assistant-service"
    PORT: int = 8089
    ENVIRONMENT: str = "production"
    DEBUG: bool = False

    # API Keys
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    DEFAULT_LLM_PROVIDER: str = "gemini"

    LOCAL_LLM_BASE_URL: str = ""
    LOCAL_LLM_MODEL: str = ""

    # Embedding Configuration
    EMBEDDING_PROVIDER: str = "openai"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int | None = None

    # Qdrant Vector Store Configuration
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION_PREFIX: str = "commerce_docs"

    # RAG Generation Configuration
    RAG_LLM_PROVIDER: str = ""  # Boşsa DEFAULT_LLM_PROVIDER kullanılır
    RAG_LLM_MODEL: str = ""     # Boşsa seçilen sağlayıcının varsayılan modeli kullanılır
    RAG_TEMPERATURE: float = 0.0
    RAG_MAX_OUTPUT_TOKENS: int = 400
    RAG_LLM_TIMEOUT_SEC: float = 30.0
    RAG_CONTEXT_TOKEN_BUDGET: int = 1500
    RAG_TOP_K: int = 5
    RAG_MIN_DENSE_SCORE: float | None = None
    RAG_MAX_ATTEMPTS: int = 2
    RAG_ABSTAIN_MESSAGE: str = (
        "Bu konuda dokümanlarımızda bilgi bulamadım. Sizi bir müşteri temsilcisine yönlendirebilirim."
    )
    RAG_RETRIEVAL_MODE: str = "hybrid"  # 'dense', 'sparse', 'hybrid'

    # Reranker Configuration
    RAG_RERANK_ENABLED: bool = False
    RAG_RERANK_PROVIDER: str = "cross_encoder"  # 'cross_encoder', 'cohere', 'fake'
    RAG_RERANK_MODEL: str = ""  # Boşsa sağlayıcının varsayılanı kullanılır
    RAG_RERANK_CANDIDATES: int = Field(
        default=20, ge=1, le=50, description="Retrieval'dan reranker'a gidecek aday sayısı (1..50)"
    )
    RAG_RERANK_TIMEOUT_SEC: float = 10.0  # Reranker API çağrısı zaman aşımı (saniye)
    RAG_RERANK_FAIL_OPEN: bool = True  # Hata anında orijinal retrieval sırasıyla devam et
    COHERE_API_KEY: str = ""  # Cohere sağlayıcısı için API anahtarı

    # Gateway Security Configuration
    # Ağ Geçidi Güvenlik Ayarları (Gateway Security)
    GATEWAY_INTERNAL_SECRET: str = "dgl-internal-gateway-secret-token-2026"
    GATEWAY_SECURITY_ENABLED: bool = True

    # Denetim İzi ve Tarama (Enumeration) Saldırısı Alarm Ayarları:
    # Kullanıcı kayan zaman penceresi içinde (örn. 60 sn) bu sayıda (örn. 5) reddedilen/yetkisiz
    # işlem (403, 404, ownership_mismatch) yaparsa sistem 'enumeration_suspected' alarmı üretir.
    AUDIT_DENY_THRESHOLD: int = Field(
        default=5, ge=1, description="Pencere içinde bu sayıda reddedilen erişim → enumeration alarmı"
    )
    AUDIT_DENY_WINDOW_SEC: float = Field(
        default=60.0, gt=0.0, description="Reddedilen erişimlerin sayıldığı pencere (saniye)"
    )

    # Eureka Discovery Configuration
    EUREKA_ENABLED: bool = False
    EUREKA_SERVER_URL: str = "http://localhost:8761/eureka/"
    EUREKA_PREFER_IP: bool = True
    SERVICE_HOST: str = ""
    EUREKA_RENEWAL_SEC: int = Field(default=10, ge=1, description="Heartbeat yenileme sıklığı (sn)")
    EUREKA_LEASE_SEC: int = Field(default=30, ge=1, description="Heartbeat kesilirse silinme süresi (sn)")
    EUREKA_DRAIN_SEC: int = Field(default=20, ge=0, description="SIGTERM sonrası deregister bekleme süresi (sn)")
    EUREKA_REQUEST_TIMEOUT_SEC: float = Field(default=3.0, gt=0, description="Eureka REST çağrısı timeout (sn)")

    # Config Server Configuration
    CONFIG_SERVER_ENABLED: bool = Field(
        default=False, description="Config Server entegrasyonunun aktif olup olmaması (False: ağ çağrısı yok)"
    )
    CONFIG_SERVER_URL: str = Field(
        default="http://localhost:8888/", description="Spring Cloud Config Server temel adresi (sonunda / ile)"
    )
    CONFIG_PROFILE: Literal["dev", "qa", "prod", "default", "test"] = Field(
        default="dev", description="Config Server profili (dev/qa/prod; Java servisleriyle uyumlu varsayılan dev)"
    )
    CONFIG_REQUEST_TIMEOUT_SEC: float = Field(
        default=3.0, gt=0.0, description="Config Server tekil HTTP GET zaman aşımı (sn)"
    )
    CONFIG_INITIAL_ATTEMPTS: int = Field(
        default=3, ge=1, le=10, description="Açılışta Config Server'a ilk bağlanma deneme sayısı"
    )
    CONFIG_FAIL_FAST: bool = Field(
        default=False, description="True ise açılışta Config Server'a ulaşılamazsa servis ayağa kalkmaz"
    )

    # Redis Configuration
    REDIS_ENABLED: bool = False
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""

    # Concurrency, Turn Timeout & Limits
    AGENT_TURN_TIMEOUT_SEC: float = Field(default=60.0, gt=0, description="Tüm agent sohbet turu zaman aşımı (sn)")
    RAG_TURN_TIMEOUT_SEC: float = Field(default=45.0, gt=0, description="Tüm RAG cevaplama turu zaman aşımı (sn)")
    AI_MAX_CONCURRENT_REQUESTS: int = Field(default=20, ge=1, description="Instance başına eşzamanlı LLM istek limiti")
    AI_MAX_BODY_BYTES: int = Field(default=65536, ge=1024, description="Maksimum istek gövdesi boyutu (byte, varsayılan 64KB)")

    # Token Budget Configuration
    TOKEN_BUDGET_ENABLED: bool = False
    TOKEN_BUDGET_DAILY_LIMIT: int = Field(default=50000, ge=1, description="Kullanıcı başına günlük token kotası")
    TOKEN_BUDGET_PER_MINUTE_LIMIT: int = Field(default=8000, ge=1, description="Kullanıcı başına dakikalık token kotası")
    PROVIDER_TPM_LIMIT: int = Field(default=0, ge=0, description="Tüm instance'ların ortak dakikalık token kotası (0=kapalı)")
    TOKEN_BUDGET_PROMPT_OVERHEAD: int = Field(default=1500, ge=0, description="Sistem prompt ve araçlar için tahmini token")
    TOKEN_BUDGET_FAIL_MODE: Literal["local", "closed"] = Field(
        default="local", description="Redis arızasında tutum: 'local' veya 'closed'"
    )

    @field_validator("TOKEN_BUDGET_FAIL_MODE", mode="before")
    @classmethod
    def normalize_fail_mode(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip().lower()
        return v

    # Downstream Microservices URLs
    ORDER_SERVICE_URL: str = "http://localhost:8082"
    SHIPPING_SERVICE_URL: str = "http://localhost:8085"
    DOWNSTREAM_TIMEOUT_SEC: float = 5.0

    # Agent Configuration
    AGENT_LLM_PROVIDER: str = ""  # Boşsa DEFAULT_LLM_PROVIDER kullanılır
    AGENT_LLM_MODEL: str = ""     # Boşsa seçilen sağlayıcının varsayılan modeli kullanılır
    AGENT_TEMPERATURE: float = 0.0
    AGENT_MAX_OUTPUT_TOKENS: int = 500
    AGENT_LLM_TIMEOUT_SEC: float = 30.0
    AGENT_TOOL_TIMEOUT_SEC: float = 8.0
    AGENT_POLICY_TOOL_TIMEOUT_SEC: float = 30.0
    AGENT_MAX_STEPS: int = 4
    AGENT_MAX_TOOL_RESULT_CHARS: int = 2000
    AGENT_PENDING_TTL_SEC: int = 300
    AGENT_FALLBACK_MESSAGE: str = (
        "Şu an bu isteğinizi güvenle tamamlayamadım. Sizi bir müşteri temsilcisine yönlendirebilirim."
    )

    # Support Ticket & Kafka Configuration
    TICKET_PUBLISHER: str = "log"  # 'log' veya 'kafka'
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    SUPPORT_TICKET_TOPIC: str = "support.ticket.created"

    # Observability
    OTEL_ENABLED: bool = False  # Test/dev'de kapalı; compose'ta true
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4318/v1/traces"  # TAM URL (Spring ile aynı sözleşme)
    LOG_FORMAT: Literal["json", "text"] = "text"  # compose'ta json

    # Pydantic Settings
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env içinde bilmediği bir değişken varsa hata fırlatma, görmezden gel
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
