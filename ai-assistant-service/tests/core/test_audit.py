"""Audit modülü birim testleri (write_audit, hash_args, DenyTracker)."""

import logging
from typing import Any
import pytest

from app.agent.tools.base import ToolResult
from app.agent.tools.registry import render_for_model
from app.core.audit import (
    DenyTracker,
    get_audit_logger,
    hash_args,
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
