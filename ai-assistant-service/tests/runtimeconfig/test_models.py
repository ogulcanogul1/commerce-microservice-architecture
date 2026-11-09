from typing import Any
import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.rag.generation.models import GenerationConfig
from app.runtimeconfig.models import (
    ENV_FIELD_MAP,
    AgentRuntime,
    BudgetRuntime,
    LoggingRuntime,
    RagRuntime,
    RuntimeSettings,
    pinned_paths,
)
from app.runtimeconfig.paths import flatten_paths, get_path, set_path


def test_paths_helpers() -> None:
    """flatten_paths, get_path ve set_path yardımcı fonksiyonlarını doğrular."""
    tree: dict[str, Any] = {"agent": {"max_steps": 4, "timeout": 30.0}}
    flat = flatten_paths(tree)
    assert flat == {"agent.max_steps": 4, "agent.timeout": 30.0}

    assert get_path(tree, "agent.max_steps") == 4
    with pytest.raises(KeyError):
        get_path(tree, "agent.unknown")

    set_path(tree, "rag.top_k", 5)
    assert tree["rag"]["top_k"] == 5
    assert get_path(tree, "rag.top_k") == 5


def test_from_startup_matches_settings() -> None:
    """RuntimeSettings.from_startup(settings) değerlerinin settings ile birebir eşleştiğini doğrular."""
    rt = RuntimeSettings.from_startup(settings)
    flat_rt = flatten_paths(rt.model_dump())

    for path, env_field in ENV_FIELD_MAP.items():
        assert path in flat_rt, f"{path} RuntimeSettings içinde bulunamadı"
        expected_val = getattr(settings, env_field)
        assert flat_rt[path] == expected_val, (
            f"{path} değeri ({flat_rt[path]}) settings.{env_field} ({expected_val}) ile eşleşmiyor"
        )


def test_env_field_map_integrity() -> None:
    """ENV_FIELD_MAP içindeki tüm ayarların Settings.model_fields içinde olduğunu doğrular."""
    for path, env_field in ENV_FIELD_MAP.items():
        assert env_field in Settings.model_fields, f"{env_field} Settings modelinde mevcut değil"

    # RuntimeSettings şeması içinde bu yolların geçerli olduğunu doğrula
    rt = RuntimeSettings.from_startup(settings)
    dumped = rt.model_dump()
    for path in ENV_FIELD_MAP:
        assert get_path(dumped, path) is not None or path == "rag.min_dense_score"


def test_turn_timeout_upper_limits_aligned_with_gateway() -> None:
    """Gateway TimeLimiter (70s/55s) invariant tavan sınırlarını doğrular."""
    # agent.turn_timeout_sec <= 65.0
    AgentRuntime(
        max_steps=4,
        llm_timeout_sec=30.0,
        turn_timeout_sec=65.0,
        max_output_tokens=500,
        temperature=0.0,
    )
    with pytest.raises(ValidationError):
        AgentRuntime(
            max_steps=4,
            llm_timeout_sec=30.0,
            turn_timeout_sec=65.1,
            max_output_tokens=500,
            temperature=0.0,
        )

    # rag.turn_timeout_sec <= 50.0
    RagRuntime(
        turn_timeout_sec=50.0,
        top_k=5,
        max_attempts=2,
        max_output_tokens=400,
        llm_timeout_sec=30.0,
        temperature=0.0,
        context_token_budget=1500,
    )
    with pytest.raises(ValidationError):
        RagRuntime(
            turn_timeout_sec=50.1,
            top_k=5,
            max_attempts=2,
            max_output_tokens=400,
            llm_timeout_sec=30.0,
            temperature=0.0,
            context_token_budget=1500,
        )


def test_llm_timeout_fits_turn_timeout() -> None:
    """Tekil LLM çağrısının toplam tur süresinden uzun olamayacağını doğrular."""
    # Agent
    with pytest.raises(ValidationError, match="agent.llm_timeout_sec"):
        AgentRuntime(
            max_steps=4,
            llm_timeout_sec=40.0,
            turn_timeout_sec=30.0,
            max_output_tokens=500,
            temperature=0.0,
        )

    # RAG
    with pytest.raises(ValidationError, match="rag.llm_timeout_sec"):
        RagRuntime(
            turn_timeout_sec=30.0,
            top_k=5,
            max_attempts=2,
            max_output_tokens=400,
            llm_timeout_sec=35.0,
            temperature=0.0,
            context_token_budget=1500,
        )


def test_budget_minute_limit_fits_daily_limit() -> None:
    """Dakikalık kotanın günlük kotadan büyük olamayacağını doğrular."""
    BudgetRuntime(daily_limit=1000, per_minute_limit=1000, provider_tpm_limit=0, prompt_overhead=100)
    with pytest.raises(ValidationError, match="budget.per_minute_limit"):
        BudgetRuntime(daily_limit=1000, per_minute_limit=1001, provider_tpm_limit=0, prompt_overhead=100)


def test_unknown_fields_forbidden() -> None:
    """extra='forbid' kuralı sayesinde bilinmeyen/statik alanların reddedildiğini doğrular."""
    rt_dump = RuntimeSettings.from_startup(settings).model_dump()

    # Kök seviyede bilinmeyen alan
    bad_root = {**rt_dump, "redis_host": "localhost"}
    with pytest.raises(ValidationError):
        RuntimeSettings.model_validate(bad_root)

    # Alt modelde bilinmeyen alan
    bad_child = {**rt_dump}
    bad_child["agent"] = {**bad_child["agent"], "unknown_param": 123}
    with pytest.raises(ValidationError):
        RuntimeSettings.model_validate(bad_child)


def test_rag_min_dense_score_normalization() -> None:
    """Spring Cloud Config'ten gelen boş string'in None'a çevrildiğini doğrular."""
    rag = RagRuntime(
        turn_timeout_sec=45.0,
        top_k=5,
        max_attempts=2,
        min_dense_score="",  # type: ignore[arg-type]
        max_output_tokens=400,
        llm_timeout_sec=30.0,
        temperature=0.0,
        context_token_budget=1500,
    )
    assert rag.min_dense_score is None


def test_logging_runtime_normalization() -> None:
    """LoggingRuntime seviye normalizasyonunu doğrular."""
    log_rt = LoggingRuntime(level=" debug ")  # type: ignore[arg-type]
    assert log_rt.level == "DEBUG"

    log_empty = LoggingRuntime(level="")  # type: ignore[arg-type]
    assert log_empty.level is None

    with pytest.raises(ValidationError):
        LoggingRuntime(level="TRACE")  # type: ignore[arg-type]


def test_rag_generation_overrides_compatibility() -> None:
    """generation_overrides çıktısının GenerationConfig ile tam uyumlu olduğunu doğrular."""
    rag = RagRuntime(
        turn_timeout_sec=45.0,
        top_k=7,
        max_attempts=3,
        min_dense_score=0.8,
        max_output_tokens=350,
        llm_timeout_sec=25.0,
        temperature=0.2,
        context_token_budget=2000,
    )
    overrides = rag.generation_overrides()

    for k in overrides:
        assert k in GenerationConfig.model_fields

    base_gen = GenerationConfig()
    merged = {**base_gen.model_dump(), **overrides}
    validated = GenerationConfig.model_validate(merged)

    assert validated.top_k == 7
    assert validated.max_attempts == 3
    assert validated.min_dense_score == 0.8
    assert validated.max_output_tokens == 350
    assert validated.llm_timeout_sec == 25.0
    assert validated.temperature == 0.2
    assert validated.context_token_budget == 2000


def test_runtime_settings_immutability() -> None:
    """RuntimeSettings nesnelerinin dondurulmuş (frozen) olduğunu doğrular."""
    rt = RuntimeSettings.from_startup(settings)
    with pytest.raises(ValidationError):
        rt.agent.max_steps = 2  # type: ignore[misc]


def test_secret_ban_in_runtime_settings() -> None:
    """RuntimeSettings şemasında hiçbir secret/key/password alanı bulunamaz."""
    for model_cls in [AgentRuntime, RagRuntime, BudgetRuntime, LoggingRuntime, RuntimeSettings]:
        for field_name, field_info in model_cls.model_fields.items():
            name_lower = field_name.lower()
            assert "secret" not in name_lower, f"{model_cls.__name__}.{field_name} 'secret' içeremez"
            assert "password" not in name_lower, f"{model_cls.__name__}.{field_name} 'password' içeremez"
            assert "_key" not in name_lower and not name_lower.endswith("key"), (
                f"{model_cls.__name__}.{field_name} key alanı olamaz"
            )
            if "token" in name_lower:
                # Token geçen alanlar yalnızca sayaç (int) olabilir (max_output_tokens, context_token_budget)
                assert field_info.annotation is int or field_info.annotation == int, (
                    f"{model_cls.__name__}.{field_name} string token/secret olamaz, sadece int sayaç olabilir"
                )


def test_pinned_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """pinned_paths fonksiyonunun sadece açıkça env ile ezilen alanları döndürdüğünü doğrular."""
    # Env yokken boş olmalı
    s_clean = Settings(_env_file=None)
    assert len(pinned_paths(s_clean)) == 0

    # Env verildiğinde ilgili yol pinned olmalı
    monkeypatch.setenv("AGENT_MAX_STEPS", "2")
    s_pinned = Settings(_env_file=None)
    assert pinned_paths(s_pinned) == frozenset({"agent.max_steps"})
