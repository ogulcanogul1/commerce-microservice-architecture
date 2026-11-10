"""Audit modülü birim testleri (write_audit, hash_args, DenyTracker)."""

import logging
from typing import Any
import pytest

from app.agent.tools.base import ToolResult
from app.agent.tools.registry import render_for_model
from app.core.audit import (
    DenyTracker,
    InMemoryDenyTracker,
    RedisDenyTracker,
    get_audit_logger,
    hash_args,
    set_deny_tracker,
    write_audit,
)


def test_write_audit_emits_single_json_line_with_required_fields(audit_records: list[dict[str, Any]]) -> None:
    """write_audit tek satır geçerli JSON yazar ve zorunlu alanları içerir."""
    write_audit(
        "test_event",
        user_id="123e4567-e89b-12d3-a456-426614174000",
        correlation_id="corr-abc",
        outcome="ok",
        extra_key="extra_val",
    )

    assert len(audit_records) == 1
    record = audit_records[0]
    assert record["event"] == "test_event"
    assert record["user_id"] == "123e4567-e89b-12d3-a456-426614174000"
    assert record["correlation_id"] == "corr-abc"
    assert record["outcome"] == "ok"
    assert record["extra_key"] == "extra_val"
    assert "timestamp" in record


def test_audit_logger_does_not_propagate_to_root(caplog: pytest.LogCaptureFixture) -> None:
    """Audit logger propagate=False olduğu için root handler'a (caplog) sızmamalıdır."""
    with caplog.at_level(logging.INFO):
        write_audit(
            "secret_event",
            user_id="user-secret-uuid-9999",
            correlation_id="corr-xyz",
            outcome="ok",
        )
    assert "user-secret-uuid-9999" not in caplog.text


def test_hash_args_is_stable_and_order_independent() -> None:
    """hash_args anahtar sırasından bağımsız, deterministik 16 karakterlik özet üretir."""
    h1 = hash_args({"a": 1, "b": 2})
    h2 = hash_args({"b": 2, "a": 1})
    assert h1 == h2
    assert len(h1) == 16


def test_hash_args_handles_none_and_unserializable() -> None:
    """None veya serileştirilemeyen nesneler için de güvenli şekilde özet döner."""
    h_none = hash_args(None)
    assert len(h_none) == 16

    class Unserializable:
        pass

    h_unserializable = hash_args({"obj": Unserializable()})
    assert len(h_unserializable) == 16


def test_write_audit_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Logger hata verse bile write_audit asla istisna fırlatmamalıdır."""
    def broken_logger():
        raise RuntimeError("Disk full / logger broken")

    monkeypatch.setattr("app.core.audit.get_audit_logger", broken_logger)

    # İstisna fırlatmadan sessizce log uyarısıyla sonlanmalı
    write_audit(
        "fail_safe_event",
        user_id="usr-1",
        correlation_id=None,
        outcome="ok",
    )


def test_deny_tracker_sliding_window_and_alerting() -> None:
    """DenyTracker kayan pencerede eşik aşıldığında pencere başına BİR kez alert verir."""
    current_time = [1000.0]
    tracker = DenyTracker(threshold=3, window_sec=60.0, clock=lambda: current_time[0])

    user_a = "user-a"
    user_b = "user-b"

    # 1. ve 2. ret -> eşik (3) aşılmadı
    assert not tracker.record(user_a)
    assert not tracker.record(user_a)

    # 3. ret -> eşik aşıldı! True döner (alarm)
    assert tracker.record(user_a)

    # 4. ret (aynı pencere içinde) -> alarm seli olmaması için False döner
    assert not tracker.record(user_a)

    # Farklı kullanıcı bağımsız sayılır
    assert not tracker.record(user_b)
    assert not tracker.record(user_b)
    assert tracker.record(user_b)

    # 61 saniye sonra (yeni pencere)
    current_time[0] += 61.0
    # Eski kayıtlar düştü, yeni 2 ret eşiğin altında
    assert not tracker.record(user_a)
    assert not tracker.record(user_a)
    # 3. ret tekrar alarm tetikler
    assert tracker.record(user_a)


def test_tool_result_reason_is_not_rendered_for_model() -> None:
    """ToolResult.reason alanı render_for_model çıktısında asla yer almamalıdır."""
    result = ToolResult(
        ok=False,
        error="Sipariş bulunamadı.",
        reason="ownership_mismatch",
    )
    rendered = render_for_model("get_order", result)
    assert "ownership_mismatch" not in rendered
    assert "Sipariş bulunamadı." in rendered


def test_redis_deny_tracker_distributed_instances_reach_threshold() -> None:
    """N farklı instance aynı Redis üzerinde çalıştığında eşik instance'lar arasında toplanır."""
    import fakeredis

    shared_redis = fakeredis.FakeRedis()
    current_time = [1000.0]

    # 3 farklı mikroservis instance'ı simüle ediliyor
    instance_1 = RedisDenyTracker(shared_redis, threshold=5, window_sec=60.0, clock=lambda: current_time[0])
    instance_2 = RedisDenyTracker(shared_redis, threshold=5, window_sec=60.0, clock=lambda: current_time[0])
    instance_3 = RedisDenyTracker(shared_redis, threshold=5, window_sec=60.0, clock=lambda: current_time[0])

    user = "attacker-user-id-1234"

    # İstekler instance'lar arasında dağıtılıyor (round-robin)
    assert not instance_1.record(user)  # 1. ret
    assert not instance_2.record(user)  # 2. ret
    assert not instance_3.record(user)  # 3. ret
    assert not instance_1.record(user)  # 4. ret

    # 5. ret Instance 2'ye geldiğinde toplam eşik (5) aşıldığı için alarm üretilir!
    assert instance_2.record(user)

    # 6. ret Instance 3'e geldiğinde pencere içinde alarm zaten üretildiği için mükerrer alarm basılmaz
    assert not instance_3.record(user)


def test_redis_deny_tracker_sliding_window_expiration() -> None:
    """Pencere süresi dolduğunda eski retler düşer ve sayaç sıfırlanır."""
    import fakeredis

    fake_redis = fakeredis.FakeRedis()
    current_time = [2000.0]

    tracker = RedisDenyTracker(fake_redis, threshold=3, window_sec=30.0, clock=lambda: current_time[0])
    user = "user-expire-test"

    assert not tracker.record(user)  # 1
    assert not tracker.record(user)  # 2
    assert tracker.record(user)      # 3 -> alert!

    # 31 saniye sonra pencere dışına çıkılır
    current_time[0] += 31.0

    # Yeni retler başlar
    assert not tracker.record(user)  # 1
    assert not tracker.record(user)  # 2
    assert tracker.record(user)      # 3 -> tekrar alert!


def test_redis_deny_tracker_fallback_on_redis_error_with_circuit_breaker() -> None:
    """Redis bağlantısı koptuğunda veya hata verdiğinde devre açılır ve sonraki çağrılarda Redis bloklanmaz."""
    from unittest.mock import MagicMock

    broken_redis = MagicMock()
    broken_redis.eval.side_effect = RuntimeError("Redis connection lost")

    current_time = [100.0]
    tracker = RedisDenyTracker(
        broken_redis,
        threshold=2,
        window_sec=60.0,
        clock=lambda: current_time[0],
        circuit_cooldown_sec=30.0,
    )
    user = "user-fallback"

    # İlk denemede Redis eval çağrılır, hata alır ve devre kesici açılır
    assert not tracker.record(user)
    assert broken_redis.eval.call_count == 1

    # İkinci denemede devre açık olduğundan Redis eval HİÇ çağrılmaz, doğrudan fallback çalışır
    assert tracker.record(user)  # 2. denemede yerel bellek üzerinden alarm üretir
    assert broken_redis.eval.call_count == 1  # Eval çağrısı artmadı!

    # 31 saniye sonra devre kapanır (cooldown bitti) ve tekrar Redis denenir
    current_time[0] += 31.0
    tracker.record(user)
    assert broken_redis.eval.call_count == 2


def test_redis_deny_tracker_cluster_hash_tags_used() -> None:
    """Redis anahtarları Redis Cluster'da CROSSSLOT hatası vermemek için {user_id} hash tag içermelidir."""
    from unittest.mock import MagicMock

    mock_redis = MagicMock()
    mock_redis.eval.return_value = 0

    tracker = RedisDenyTracker(mock_redis, threshold=3, window_sec=60.0)
    tracker.record("alice-42")

    assert mock_redis.eval.called
    call_args = mock_redis.eval.call_args[0]
    window_key = call_args[2]
    alerted_key = call_args[3]

    assert window_key == "audit:deny:{alice-42}:window"
    assert alerted_key == "audit:deny:{alice-42}:alerted"


@pytest.mark.anyio
async def test_record_denied_access_async(monkeypatch: pytest.MonkeyPatch, audit_records: list[dict[str, Any]]) -> None:
    """record_denied_access async çalışmalı ve event loop'u bloklamadan audit alarmı basmalıdır."""
    from app.core.audit import record_denied_access, InMemoryDenyTracker, set_deny_tracker

    tracker = InMemoryDenyTracker(threshold=2, window_sec=60.0)
    set_deny_tracker(tracker)

    await record_denied_access("user-async-1", "corr-async-1")
    assert not any(r.get("event") == "enumeration_suspected" for r in audit_records)

    await record_denied_access("user-async-1", "corr-async-1")
    alerts = [r for r in audit_records if r.get("event") == "enumeration_suspected"]
    assert len(alerts) == 1
    assert alerts[0]["user_id"] == "user-async-1"
    assert alerts[0]["correlation_id"] == "corr-async-1"

