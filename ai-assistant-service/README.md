# AI Assistant Service (`ai-assistant-service`)

Commerce Platform Poliglot Yapay Zeka Alışveriş ve Destek Asistanı Servisi.

## Teknoloji Yığını
- **Python 3.14+**
- **FastAPI**
- **Pydantic & Pydantic Settings**
- **Uvicorn**
- Paket Yöneticisi: **Astral `uv`**

## Yerel Geliştirme

```powershell
cd ai-assistant-service

# Bağımlılıkları senkronize et
uv sync

# Servisi başlat (Port: 8089)
uv run uvicorn app.main:app --reload --port 8089
```

- Sağlık Kontrolü: `http://localhost:8089/health`
- Swagger UI Dokümantasyonu: `http://localhost:8089/docs`
