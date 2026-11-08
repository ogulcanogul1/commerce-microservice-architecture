"""FastAPI Depends mekanizması için token bütçesi bağımlılık fonksiyonları."""

from __future__ import annotations

import uuid

from fastapi import Header, Request

from app.budget.service import TokenBudgetService


def get_budget_subject(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> str:
    """İstek başlığındaki 'X-User-Id' değerini bütçe kimliğine (subject) dönüştürür.
    
    Kurallar:
    - Geçerli bir UUID ise küçük harfe normalize edilmiş UUID string'i döner.
    - Boş veya geçersizse 'anonymous' döner (/rag/answer uç noktası kimlik doğrulaması zorunlu tutmadığı için).
    """
    if not x_user_id:
        return "anonymous"

    try:
        val = uuid.UUID(str(x_user_id).strip())
        return str(val).lower()
    except (ValueError, AttributeError):
        return "anonymous"


def get_token_budget(request: Request) -> TokenBudgetService | None:
    """FastAPI endpoint'lerinde 'budget: TokenBudgetService | None = Depends(get_token_budget)'
    şeklinde app.state üzerindeki bütçe servisine erişmeyi sağlar.
    
    TOKEN_BUDGET_ENABLED=False iken None döner.
    """
    return getattr(request.app.state, "token_budget", None)
