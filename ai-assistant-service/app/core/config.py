from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Service Identity
    SERVICE_NAME: str = "ai-assistant-service"
    SERVICE_HOST: str = "localhost"
    SERVICE_PORT: int = 8089
    ENVIRONMENT: str = "dev"

    # Eureka Discovery
    EUREKA_ENABLED: bool = False
    EUREKA_SERVER_URL: str = "http://localhost:8761/eureka/"

    # Gateway & Downstream Services
    GATEWAY_SECRET_ENABLED: bool = True
    GATEWAY_INTERNAL_SECRET: str = "dgl-internal-gateway-secret-token-2026"
    GATEWAY_BASE_URL: str = "http://localhost:8080"
    ORDER_SERVICE_URL: str = "http://localhost:8082"
    PRODUCT_SERVICE_URL: str = "http://localhost:8081"
    SHIPPING_SERVICE_URL: str = "http://localhost:8085"
    INVENTORY_SERVICE_URL: str = "http://localhost:8084"
    PAYMENT_SERVICE_URL: str = "http://localhost:8083"

    # Redis Session Store
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    SESSION_TTL_SECONDS: int = 1800

    # Apache Kafka
    KAFKA_ENABLED: bool = False
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_SUPPORT_TOPIC: str = "support.ticket.created"

    # OpenTelemetry
    OTEL_ENABLED: bool = False
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4318/v1/traces"

    # LLM Providers
    DEFAULT_LLM_PROVIDER: str = "gemini"
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-3-5-sonnet-latest"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"
    LOCAL_LLM_URL: str = "http://localhost:11434/v1"
    LOCAL_LLM_MODEL: str = "llama3.2"


settings = Settings()
