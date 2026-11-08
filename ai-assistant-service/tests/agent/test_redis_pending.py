"""RedisPendingActionStore birim testleri (FakeRedis & Lua scriptleri)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import fakeredis
import pytest

from app.agent.models import ActionType, PendingAction
from app.agent.redis_pending import RedisPendingActionStore

USER_A = "11111111-1111-1111-1111-111111111111"
USER_B = "22222222-2222-2222-2222-222222222222"


def _make_action(action_id: str = "act_test_123", ttl_sec: int = 300) -> PendingAction:
    now = datetime.now(timezone.utc)
    return PendingAction(
        action_id=action_id,
        user_id=USER_A,
        action_type="cancel_order",
        summary="Sipariş İptali (ORD-123)",
        params={"order_id": "ORD-123", "reason": "Müşteri vazgeçti"},
        created_at=now,
        expires_at=now + timedelta(seconds=ttl_sec),
    )


def test_redis_pending_action_create_and_consume():
    """Aksiyon başarıyla kaydedilir ve tek seferde tüketilir."""
    fake_redis = fakeredis.FakeRedis()
    store = RedisPendingActionStore(fake_redis)

    action = _make_action()
    store.create(action)

    consumed = store.consume(action.action_id, USER_A)
    assert consumed is not None
    assert consumed.action_id == action.action_id
    assert consumed.user_id == USER_A
    assert consumed.params["order_id"] == "ORD-123"

    # Çift yürütme koruması: İkinci kez çağrıldığında None dönmelidir
    consumed_again = store.consume(action.action_id, USER_A)
    assert consumed_again is None


def test_redis_pending_action_cross_user_isolation():
    """Başka bir kullanıcı aksiyonu tüketemez ve aksiyon silinmez."""
    fake_redis = fakeredis.FakeRedis()
    store = RedisPendingActionStore(fake_redis)

    action = _make_action()
    store.create(action)

    # Başka kullanıcı (USER_B) tüketmeye çalışıyor
    stolen = store.consume(action.action_id, USER_B)
    assert stolen is None

    # Güvenlik Kuralı: Asıl sahibi (USER_A) hâlâ tüketebilmelidir
    legitimate = store.consume(action.action_id, USER_A)
    assert legitimate is not None
    assert legitimate.action_id == action.action_id


def test_redis_pending_action_discard():
    """Kullanıcı aksiyonu iptal ettiğinde Redis'ten silinir."""
    fake_redis = fakeredis.FakeRedis()
    store = RedisPendingActionStore(fake_redis)

    action = _make_action()
    store.create(action)

    # USER_B iptal edemez
    assert store.discard(action.action_id, USER_B) is False

    # USER_A iptal edebilir
    assert store.discard(action.action_id, USER_A) is True

    # İptal edildiği için artık consume edilemez
    assert store.consume(action.action_id, USER_A) is None


def test_redis_pending_action_restore():
    """Geçici hata alan işlem geri yüklenir ve tekrar tüketilebilir."""
    fake_redis = fakeredis.FakeRedis()
    store = RedisPendingActionStore(fake_redis)

    action = _make_action()
    store.create(action)

    consumed = store.consume(action.action_id, USER_A)
    assert consumed is not None

    # Downstream 503 aldı, restore ediyoruz
    store.restore(consumed)

    # Tekrar tüketilebilmeli
    retried = store.consume(action.action_id, USER_A)
    assert retried is not None
    assert retried.action_id == action.action_id


def test_redis_pending_action_multi_instance_sharing():
    """İki farklı sunucu örneği (instance) aynı Redis üzerinden aksiyon paylaşabilir."""
    fake_redis = fakeredis.FakeRedis()

    # Instance 1 (Container A)
    instance_a = RedisPendingActionStore(fake_redis)
    # Instance 2 (Container B)
    instance_b = RedisPendingActionStore(fake_redis)

    action = _make_action("act_multi_server_999")

    # Container A aksiyonu oluşturur
    instance_a.create(action)

    # Container B aksiyonu tüketir
    consumed_by_b = instance_b.consume(action.action_id, USER_A)
    assert consumed_by_b is not None
    assert consumed_by_b.action_id == action.action_id

    # Container A tekrar bakarsa artık silinmiştir
    assert instance_a.consume(action.action_id, USER_A) is None
