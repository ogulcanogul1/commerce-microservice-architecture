"""Prometheus metrikleri ve HTTP metrik middleware modülü.

Bu modül, mikroservisin çalışma zamanı performansını ve kaynak kullanımını
Prometheus formatında ölçer:
1. `http_server_requests_seconds`: Gelen tüm HTTP isteklerinin süresi, durum kodu ve route şablonu (Micrometer uyumlu).
2. `ai_tool_call_duration_seconds`: Ajanın (Agent) çalıştırdığı araçların işlem süresi ve sonucu.
3. `ai_llm_request_duration_seconds`: Harici LLM sağlayıcılarına yapılan ağ çağrılarının gecikmesi.
4. `ai_llm_tokens_total`: Modele giden (input) ve modelden gelen (output) token miktarları.

MİMARİ VE KARDİNALİTE KURALLARI:
- Etiket (label) olarak user_id, trace_id, sipariş numarası veya dinamik URL path ASLA KULLANILMAZ.
- HTTP path'leri daima Starlette route şablonuna (`/agent/actions/{action_id}/confirm`) normalize edilir.
- Bilinmeyen veya model tarafından uydurulan tool adları 'unknown' etiketine indirgenir.
- 'application' etiketi kodda tanımlanmaz; Prometheus scrape yapılandırması tarafından statik eklenir.
"""

import time
from prometheus_client import Counter, Histogram
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# İstek süreleri için standart logaritmik gecikme (latency) sepetleri (saniye cinsinden)
_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)

# 1. HTTP Sunucu İstekleri Histogramı (Micrometer sözleşmesiyle birebir aynı)
HTTP_SERVER_REQUESTS = Histogram(
    "http_server_requests_seconds",
    "HTTP sunucu istek süresi ve dağılımı (Micrometer uyumlu)",
    ["method", "uri", "status", "outcome"],
    buckets=_BUCKETS,
)

# 2. Agent Araç (Tool) Çağrı Süresi Histogramı
AI_TOOL_CALL_DURATION = Histogram(
    "ai_tool_call_duration_seconds",
    "Agent tarafından yürütülen araç çağrılarının süresi",
    ["tool_name", "outcome"],
    buckets=_BUCKETS,
)

# 3. LLM Sağlayıcı Çağrı Süresi Histogramı
AI_LLM_REQUEST_DURATION = Histogram(
    "ai_llm_request_duration_seconds",
    "Büyük Dil Modeli (LLM) ağ çağrılarının yanıt süresi",
    ["provider", "outcome"],
    buckets=_BUCKETS,
)

# 4. LLM Token Tüketim Sayacı
AI_LLM_TOKENS = Counter(
    "ai_llm_tokens_total",
    "Harcanan toplam LLM token sayısı",
    ["provider", "direction"],  # direction: 'input' (prompt) | 'output' (completion)
)

# Metrik toplanmayacak probe ve scrape yolları (metriklerin kendini ölçüp şişmesini engeller)
_EXCLUDED_METRIC_PATHS = (
    "/health",
    "/actuator/prometheus",
    "/actuator/health",
    "/actuator/health/liveness",
    "/actuator/health/readiness",
)


class HttpMetricsMiddleware:
    """Tüm HTTP isteklerinin süresini ölçen ve route şablonunu çıkaran saf ASGI middleware.

    Kardinalite Koruması:
    Eğer kullanıcı `/agent/orders/ORD-12345` çağırırsa, bu etiket olarak ham path ile
    kaydedilirse milyonlarca farklı time-series oluşur. Bu middleware, istek tamamlandıktan sonra
    Starlette'in rota eşleyicisinden (`scope.get('route')`) şablonu (`/agent/orders/{order_number}`)
    alır. Rota eşleşmezse (404 Not Found) sabit 'UNMATCHED' değerini kullanır.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Sadece HTTP isteklerini ölç
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        raw_path = scope.get("path", "")
        # Probe ve prometheus scrape yollarını ölçüm dışı bırak
        if any(raw_path == p or raw_path.startswith(p + "/") for p in _EXCLUDED_METRIC_PATHS):
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "UNKNOWN")
        status_code = 500  # Varsayılan: İstisna durumunda 500 kabul edilir
        start_time = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 500)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed = time.perf_counter() - start_time

            # 1. Rota şablonunu (URI template) çıkar (Kardinalite kontrolü)
            route = scope.get("route")
            if route is not None and hasattr(route, "path"):
                uri = route.path
            else:
                uri = "UNMATCHED"

            # 2. HTTP sonucunu (outcome) kategorize et (Spring Boot Actuator standardı)
            if 200 <= status_code < 300:
                outcome = "SUCCESS"
            elif 300 <= status_code < 400:
                outcome = "REDIRECTION"
            elif 400 <= status_code < 500:
                outcome = "CLIENT_ERROR"
            elif 500 <= status_code < 600:
                outcome = "SERVER_ERROR"
            else:
                outcome = "UNKNOWN"

            # 3. Metriği gözlemle ve histograma ekle
            HTTP_SERVER_REQUESTS.labels(
                method=method,
                uri=uri,
                status=str(status_code),
                outcome=outcome,
            ).observe(elapsed)
