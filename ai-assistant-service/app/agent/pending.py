"""Pending action store for human-in-the-loop confirmation.

Holds sensitive actions (cancellations, tickets) until the user explicitly confirms.
Uses atomic pop (consume) to prevent double execution and race conditions.
"""

from collections import OrderedDict
from collections.abc import Callable
from datetime import datetime, timezone
import threading
from typing import Protocol

from app.agent.models import PendingAction


class PendingActionStore(Protocol):
    """Protocol contract for pending action storage."""

    def create(self, action: PendingAction) -> PendingAction:
        """Store a pending action or return existing matching action."""
        ...

    def consume(self, action_id: str, user_id: str) -> PendingAction | None:
        """Atomically retrieve and delete pending action if ownership and TTL match."""
        ...

    def discard(self, action_id: str, user_id: str) -> bool:
        """Discard/reject a pending action."""
        ...


class InMemoryPendingActionStore:
    """Thread-safe, in-memory pending action store with atomic consume, dedup, and TTL eviction."""

    def __init__(
        self,
        ttl_sec: int = 300,
        max_items: int = 1000,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._ttl_sec = ttl_sec
        self._max_items = max_items
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.Lock()
        # OrderedDict used to track LRU/insertion order for max_items eviction
        self._actions: OrderedDict[str, PendingAction] = OrderedDict()

    def _cleanup_expired(self, now: datetime) -> None:
        """Evict expired actions. Assumes lock is already acquired."""
        expired_ids = [
            action_id
            for action_id, action in self._actions.items()
            if action.expires_at <= now
        ]
        for aid in expired_ids:
            del self._actions[aid]

    def create(self, action: PendingAction) -> PendingAction:
        """Store pending action with dedup check and capacity eviction."""
        now = self._clock()
        with self._lock:
            self._cleanup_expired(now)

            # Çift tıklama / model tekrarı kontrolü: Aynı kullanıcı ve aynı parametreler varsa mevcut olanı dön
            for existing in self._actions.values():
                if (
                    existing.user_id == action.user_id
                    and existing.action_type == action.action_type
                    and existing.params == action.params
                    and existing.expires_at > now
                ):
                    return existing

            # Kapasite sınırı aşılırsa en eski kaydı temizle
            if len(self._actions) >= self._max_items:
                self._actions.popitem(last=False)

            self._actions[action.action_id] = action
            return action

    def consume(self, action_id: str, user_id: str) -> PendingAction | None:
        """Atomically pop the pending action if ownership and expiration criteria pass.

        Security note: If caller's user_id does not match, the action is NOT deleted
        so the legitimate owner can still confirm it.
        """
        now = self._clock()
        with self._lock:
            action = self._actions.get(action_id)
            if action is None:
                return None

            # Süresi dolmuşsa sil ve None dön
            if action.expires_at <= now:
                del self._actions[action_id]
                return None

            # Başka kullanıcının denemesi ise kaydı silme, yalnızca None dön
            if action.user_id.lower() != user_id.lower():
                return None

            # Tek kullanımlık: Başarılı tüketimde atomik olarak sil
            return self._actions.pop(action_id)

    def discard(self, action_id: str, user_id: str) -> bool:
        """Discard/cancel pending action if caller is the legitimate owner."""
        now = self._clock()
        with self._lock:
            action = self._actions.get(action_id)
            if action is None or action.expires_at <= now:
                return False

            if action.user_id.lower() != user_id.lower():
                return False

            del self._actions[action_id]
            return True
