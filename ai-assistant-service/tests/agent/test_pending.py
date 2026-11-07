from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import pytest

from app.agent.models import PendingAction
from app.agent.pending import InMemoryPendingActionStore


def _sample_action(
    action_id: str = "act-1",
    user_id: str = "user-1",
    action_type: str = "cancel_order",
    expires_in_sec: int = 300,
) -> PendingAction:
    now = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    return PendingAction(
        action_id=action_id,
        user_id=user_id,
        action_type=action_type,  # type: ignore[arg-type]
        params={"order_number": "ORD-1"},
        summary="İptal onayı?",
        created_at=now,
        expires_at=now + timedelta(seconds=expires_in_sec),
    )


def test_pending_store_create_and_single_use_consume() -> None:
    now = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    store = InMemoryPendingActionStore(clock=lambda: now)
    action = _sample_action()

    store.create(action)

    # 1. Başarılı tüketim (consume)
    consumed = store.consume("act-1", user_id="user-1")
    assert consumed is not None
    assert consumed.action_id == "act-1"

    # 2. İkinci tüketim başarısız olmalı (tek kullanımlık - replay koruması)
    assert store.consume("act-1", user_id="user-1") is None


def test_pending_store_unauthorized_user_does_not_evict_action() -> None:
    now = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    store = InMemoryPendingActionStore(clock=lambda: now)
    action = _sample_action(user_id="user-1")
    store.create(action)

    # Başka bir kullanıcı tüketmeye çalışırsa None dönmeli
    assert store.consume("act-1", user_id="user-ATTACKER") is None

    # Güvenlik: Asıl hak sahibi hâlâ tüketebilmeli (kayıt yanmamalı)
    legit = store.consume("act-1", user_id="user-1")
    assert legit is not None
    assert legit.action_id == "act-1"


def test_pending_store_ttl_expiration() -> None:
    current_time = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    store = InMemoryPendingActionStore(clock=lambda: current_time)

    # 60 saniyelik aksiyon
    action = _sample_action(expires_in_sec=60)
    store.create(action)

    # 61 saniye sonraya ilerlet
    current_time += timedelta(seconds=61)

    # Süresi dolduğu için bulunamamalı
    assert store.consume("act-1", user_id="user-1") is None


def test_pending_store_duplicate_proposal_returns_existing() -> None:
    now = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    store = InMemoryPendingActionStore(clock=lambda: now)

    act1 = _sample_action(action_id="act-FIRST")
    act2 = _sample_action(action_id="act-SECOND")  # Aynı user, type ve params

    stored1 = store.create(act1)
    stored2 = store.create(act2)

    # Çift tıklamada veya model tekrarında ilk aksiyon korunmalı
    assert stored2.action_id == stored1.action_id
    assert stored2.action_id == "act-FIRST"


def test_pending_store_max_items_eviction() -> None:
    now = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    store = InMemoryPendingActionStore(max_items=2, clock=lambda: now)

    a1 = PendingAction(
        action_id="a1",
        user_id="u1",
        action_type="cancel_order",
        params={"id": "1"},
        summary="s1",
        created_at=now,
        expires_at=now + timedelta(seconds=300),
    )
    a2 = PendingAction(
        action_id="a2",
        user_id="u2",
        action_type="cancel_order",
        params={"id": "2"},
        summary="s2",
        created_at=now,
        expires_at=now + timedelta(seconds=300),
    )
    a3 = PendingAction(
        action_id="a3",
        user_id="u3",
        action_type="cancel_order",
        params={"id": "3"},
        summary="s3",
        created_at=now,
        expires_at=now + timedelta(seconds=300),
    )

    store.create(a1)
    store.create(a2)
    store.create(a3)  # a1 silinmeli

    assert store.consume("a1", user_id="u1") is None
    assert store.consume("a2", user_id="u2") is not None
    assert store.consume("a3", user_id="u3") is not None


def test_pending_store_concurrent_consume_race_condition() -> None:
    now = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    store = InMemoryPendingActionStore(clock=lambda: now)
    action = _sample_action()
    store.create(action)

    results: list[PendingAction | None] = []

    def try_consume() -> PendingAction | None:
        return store.consume("act-1", user_id="user-1")

    # 50 thread aynı anda consume denerse
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(try_consume) for _ in range(50)]
        for f in futures:
            results.append(f.result())

    # Tam olarak 1 thread başarılı olmalı, diğer 49'u None dönmeli
    successes = [r for r in results if r is not None]
    assert len(successes) == 1
