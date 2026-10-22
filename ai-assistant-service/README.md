# AI Assistant Service (`ai-assistant-service`)

Commerce Platform'un Java 21 / Spring Boot mikroservis ekosistemine entegre, **Python 3.12 + FastAPI + `uv`** tabanlı Poliglot Yapay Zeka Ajan Servisi.

## Hızlı Başlangıç (`uv` ile)

```powershell
cd ai-assistant-service

# Bağımlılıkları senkronize et ve sanal ortamı oluştur (.venv)
uv sync

# Uygulamayı yerel ortamda başlat (Port: 8089)
uv run uvicorn app.main:app --reload --port 8089

# Testleri çalıştır
uv run pytest
```
