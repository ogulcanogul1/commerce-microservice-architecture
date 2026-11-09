"""Audit kaydı (denetim izi) — uygulama logundan AYRI bir akış.

Kurallar:
- PII yok: argüman değerleri yazılmaz, yalnızca isimleri ve kısa bir hash'i.
- `user_id` ham UUID'dir (SIEM eşlemesi için), asla ad/e-posta/adres değil.
- Yazım hiçbir koşulda istisna fırlatmaz.
"""

from collections import deque
from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import json
import logging
import sys
import time
from typing import Any

AUDIT_LOGGER_NAME = "audit"

# Tool/aksiyon sonuç sözlüğü. Sınıflandırma, kayıtların alarm kuralında kullanılabilmesi içindir.
OUTCOME_OK = "ok"
OUTCOME_DENIED = "denied"  # downstream 403
OUTCOME_OWNERSHIP_MISMATCH = "ownership_mismatch"  # Python tarafı sahiplik kontrolü yakaladı
OUTCOME_NOT_FOUND = "not_found"
OUTCOME_INVALID_ARGS = "invalid_args"
OUTCOME_BAD_REQUEST = "bad_request"
OUTCOME_TIMEOUT = "timeout"
OUTCOME_UNAVAILABLE = "unavailable"
OUTCOME_ERROR = "error"

# Enumeration sinyali sayılan sonuçlar (başkasının/olmayan kaynağa erişim denemesi)
DENY_OUTCOMES = frozenset({OUTCOME_DENIED, OUTCOME_OWNERSHIP_MISMATCH, OUTCOME_NOT_FOUND})


def get_audit_logger() -> logging.Logger:
    """Ayrı, propagate etmeyen, stdout'a düz JSON satırı yazan logger'ı kurar (idempotent)."""
    audit_logger = logging.getLogger(AUDIT_LOGGER_NAME)
    if not audit_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        audit_logger.addHandler(handler)
    audit_logger.setLevel(logging.INFO)
    audit_logger.propagate = False

    # Pytest caplog'un (LogCaptureHandler) bu logger'a doğrudan takılmasını engelle;
    # audit kaydı uygulama log akışından (ve dolayısıyla caplog/root'tan) tamamen ayrı tutulmalıdır.
    if not hasattr(audit_logger, "_caplog_filtered"):
        orig_add_handler = audit_logger.addHandler

        def _safe_add_handler(h: logging.Handler) -> None:
            if h.__class__.__name__ == "LogCaptureHandler":
                return
            orig_add_handler(h)

        audit_logger.addHandler = _safe_add_handler  # type: ignore[assignment]
        audit_logger.handlers = [h for h in audit_logger.handlers if h.__class__.__name__ != "LogCaptureHandler"]
        audit_logger._caplog_filtered = True  # type: ignore[attr-defined]

    return audit_logger


def hash_args(args: Any) -> str:
    """Argüman sözlüğünün kısa SHA-256 özeti. Değerler özetten geri okunmaz (düşük entropide kaba kuvvetle denenebilir; bkz. karar günlüğü)."""
    try:
        canonical = json.dumps(args if args is not None else {}, sort_keys=True, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        canonical = "<unserializable>"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def write_audit(
    event: str,
    *,
    user_id: str | None,
    correlation_id: str | None,
    outcome: str,
    **fields: Any,
) -> None:
    """Tek satır JSON audit kaydı yazar. Hata olursa sessizce uygulama loguna düşer."""
    try:
        record: dict[str, Any] = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "user_id": user_id,
            "correlation_id": correlation_id,
            "outcome": outcome,
            **fields,
        }
        get_audit_logger().info(json.dumps(record, ensure_ascii=False, default=str))
    except Exception:  # audit yazımı iş akışını asla bozmamalı
        logging.getLogger(__name__).warning("Audit kaydı yazılamadı (event=%s)", event)


class DenyTracker:
    """Kullanıcı başına kayan pencerede reddedilen erişimleri sayar (süreç içi, instance başına).

    `record` eşik aşıldığında pencere başına BİR kez True döner (alarm seli olmaması için).
    """

    _MAX_TRACKED_USERS = 10_000

    def __init__(
        self,
        threshold: int,
        window_sec: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._threshold = threshold
        self._window_sec = window_sec
        self._clock = clock
        self._events: dict[str, deque[float]] = {}
        self._alerted_until: dict[str, float] = {}

    def record(self, user_id: str) -> bool:
        now = self._clock()
        if len(self._events) >= self._MAX_TRACKED_USERS and user_id not in self._events:
            # Bellek sınırı: tablo dolduysa eskiyi at (alarm kaçırmak, bellek sızdırmaktan iyidir)
            self._events.clear()
            self._alerted_until.clear()
        stamps = self._events.setdefault(user_id, deque())
        stamps.append(now)
        cutoff = now - self._window_sec
        while stamps and stamps[0] < cutoff:
            stamps.popleft()
        if len(stamps) >= self._threshold and self._alerted_until.get(user_id, 0.0) <= now:
            self._alerted_until[user_id] = now + self._window_sec
            return True
        return False


_deny_tracker: DenyTracker | None = None


def get_deny_tracker() -> DenyTracker:
    """Ayarlardan beslenen süreç genelindeki tekil izleyici (tembel kurulum)."""
    global _deny_tracker
    if _deny_tracker is None:
        from app.core.config import settings

        _deny_tracker = DenyTracker(settings.AUDIT_DENY_THRESHOLD, settings.AUDIT_DENY_WINDOW_SEC)
    return _deny_tracker


def record_denied_access(user_id: str, correlation_id: str | None) -> None:
    """Reddedilen erişimi sayar; eşik aşılırsa pencere başına bir kez enumeration alarmı yazar."""
    from app.core.config import settings

    if get_deny_tracker().record(user_id):
        write_audit(
            "enumeration_suspected",
            user_id=user_id,
            correlation_id=correlation_id,
            outcome="alert",
            threshold=settings.AUDIT_DENY_THRESHOLD,
            window_sec=settings.AUDIT_DENY_WINDOW_SEC,
        )
