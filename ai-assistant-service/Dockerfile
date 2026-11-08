FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Hızlı paket yöneticisi uv resmi imajından kopyalanır
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Bağımlılıkları önbelleklemek (caching) için kilit dosyalarını kopyalayıp kuruyoruz
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Uygulama kaynak kodunu kopyalıyoruz
COPY app ./app

EXPOSE 8089

# KRİTİK: TEK worker (--workers verilmez)!
# Çoklu worker aynı instance'ı Eureka'ya birden fazla kez kaydeder ve heartbeat çakışır.
# Mikroservis ölçeklemesi konteyner replikaları (--scale) üzerinden yapılır.
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8089", "--timeout-graceful-shutdown", "75"]
