"""RedisPendingActionStore birim testleri (FakeRedis, Lua scriptleri, hata yayılımı ve dedup)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import fakeredis
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError, RedisError

from app.agent.models import ActionType, PendingAction
from app.agent.pending import PendingActionStoreError
from app.agent.redis_pending import RedisPendingActionStore

USER_A = "11111111-1111-1111-1111-111111111111"
USER_B = "22222222-2222-2222-2222-222222222222"


def _make_action(
    action_id: str = "act_test_123",
    user_id: str = USER_A,
    action_type: ActionType = "cancel_order",
    order_id: str = "ORD-123",
    ttl_sec: int = 300,
) -> PendingAction:
    now = datetime.now(timezone.utc)
    return PendingAction(
        action_id=action_id,
        user_id=user_id,
        action_type=action_type,
        summary=f"Sipariş İptali ({order_id})",
        params={"order_id": order_id, "reason": "Müşteri vazgeçti"},
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


def test_redis_pending_action_deduplication():
    """Aynı kullanıcı, aynı aksiyon türü ve parametrelerle mükerrer teklif gelirse mevcut aksiyon döner."""
    fake_redis = fakeredis.FakeRedis()
    store = RedisPendingActionStore(fake_redis)

    act1 = _make_action(action_id="act_first", order_id="ORD-999")
    act2 = _make_action(action_id="act_second", order_id="ORD-999")

    stored1 = store.create(act1)
    stored2 = store.create(act2)

    assert stored1.action_id == "act_first"
    # İkinci create aynı parametreleri tespit edip ilkini döndürmeli
    assert stored2.action_id == stored1.action_id
    assert stored2.action_id == "act_first"


def test_redis_pending_action_dedup_cleared_after_consume():
    """Aksiyon tüketildikten sonra aynı parametrelerle yeni aksiyon oluşturulabilmelidir."""
    fake_redis = fakeredis.FakeRedis()
    store = RedisPendingActionStore(fake_redis)

    act1 = _make_action(action_id="act_first", order_id="ORD-100")
    store.create(act1)

    # Tüketildi
    consumed = store.consume(act1.action_id, USER_A)
    assert consumed is not None

    # Şimdi aynı parametrelerle yeni aksiyon açılabilir
    act2 = _make_action(action_id="act_new", order_id="ORD-100")
    stored2 = store.create(act2)
    assert stored2.action_id == "act_new"


def test_redis_pending_action_dedup_cleared_after_discard():
    """Aksiyon reddedildikten sonra aynı parametrelerle yeni aksiyon oluşturulabilmelidir."""
    fake_redis = fakeredis.FakeRedis()
    store = RedisPendingActionStore(fake_redis)

    act1 = _make_action(action_id="act_first", order_id="ORD-200")
    store.create(act1)

    # İptal edildi
    assert store.discard(act1.action_id, USER_A) is True

    # Yeni aksiyon açılabilir
    act2 = _make_action(action_id="act_new", order_id="ORD-200")
    stored2 = store.create(act2)
    assert stored2.action_id == "act_new"


def test_redis_pending_action_error_propagation_create():
    """Redis bağlantı hatasında create sessizce yutulmaz, PendingActionStoreError fırlatır."""
    mock_redis = MagicMock()
    mock_redis.eval.side_effect = RedisConnectionError("Redis connection lost")
    store = RedisPendingActionStore(mock_redis)

    action = _make_action()
    with pytest.raises(PendingActionStoreError, match="Failed to store pending action"):
        store.create(action)


def test_redis_pending_action_error_propagation_consume():
    """Redis bağlantı hatasında consume sessizce None dönmez, PendingActionStoreError fırlatır."""
    mock_redis = MagicMock()
    mock_redis.eval.side_effect = RedisConnectionError("Redis connection lost")
    store = RedisPendingActionStore(mock_redis)

    with pytest.raises(PendingActionStoreError, match="Failed to consume pending action"):
        store.consume("act_123", USER_A)


def test_redis_pending_action_error_propagation_discard():
    """Redis bağlantı hatasında discard sessizce False dönmez, PendingActionStoreError fırlatır."""
    mock_redis = MagicMock()
    mock_redis.eval.side_effect = RedisConnectionError("Redis connection lost")
    store = RedisPendingActionStore(mock_redis)

    with pytest.raises(PendingActionStoreError, match="Failed to discard pending action"):
        store.discard("act_123", USER_A)


def test_redis_pending_action_error_propagation_restore():
    """Redis bağlantı hatasında restore sessizce yutulmaz, PendingActionStoreError fırlatır."""
    mock_redis = MagicMock()
    mock_pipeline = MagicMock()
    mock_pipeline.execute.side_effect = RedisConnectionError("Redis connection lost")
    mock_redis.pipeline.return_value = mock_pipeline
    store = RedisPendingActionStore(mock_redis)

    action = _make_action()
    with pytest.raises(PendingActionStoreError, match="Failed to restore pending action"):
        store.restore(action)
