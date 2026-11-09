import pytest

from app.runtimeconfig.parsing import (
    ConfigFormatError,
    extract_runtime_tree,
    merge_property_sources,
)


def test_first_source_has_highest_precedence() -> None:
    """Config Server'ın en baştaki kaynağının (prod/dev) en yüksek önceliğe sahip olduğunu doğrular."""
    sources = [
        {"name": "ai-assistant-service-prod.yaml", "source": {"ai.agent.max-steps": 8}},
        {"name": "ai-assistant-service.yaml", "source": {"ai.agent.max-steps": 5, "ai.rag.top-k": 7}},
        {"name": "application.yaml", "source": {"ai.rag.top-k": 3, "gateway.internal.secret": "${X:y}"}},
    ]

    merged = merge_property_sources(sources)
    # Baştaki prod değeri (8) ve temel yaml değeri (7) kazanmalı
    assert merged["ai.agent.max-steps"] == 8
    assert merged["ai.rag.top-k"] == 7

    tree = extract_runtime_tree(merged)
    assert tree == {
        "agent": {"max_steps": 8},
        "rag": {"top_k": 7},
    }
    # gateway anahtarı elenmiş olmalı ve çözülmemiş placeholder hata vermemiş olmalı (çünkü ai. önekli değil)
    assert "gateway" not in tree


def test_extract_runtime_tree_rejects_list_syntax() -> None:
    """Liste sözdizimi içeren ai.* anahtarlarının reddedildiğini doğrular."""
    with pytest.raises(ConfigFormatError, match="Liste anahtarları desteklenmiyor"):
        extract_runtime_tree({"ai.items[0]": "test"})


def test_extract_runtime_tree_rejects_unresolved_placeholder() -> None:
    """ai.* altında çözülmemiş placeholder varsa hata vermeli ve hata mesajında gizli değer sızmamalıdır."""
    with pytest.raises(ConfigFormatError) as exc_info:
        extract_runtime_tree({"ai.agent.max-steps": "${MAX_STEPS:4}"})

    assert "Çözülmemiş placeholder tespit edildi: ai.agent.max-steps" in str(exc_info.value)
    # Mesajda değer yer almamalıdır
    assert "${MAX_STEPS:4}" not in str(exc_info.value)


def test_extract_runtime_tree_rejects_leaf_branch_conflict() -> None:
    """Aynı yolun hem dal hem yaprak olarak tanımlanması durumunda hata fırlatmalıdır."""
    # ai.agent önce tekil değer, sonra alt dal
    with pytest.raises(ConfigFormatError, match="Çakışan konfigürasyon yolu"):
        extract_runtime_tree({"ai.agent": 5, "ai.agent.max-steps": 4})


def test_extract_runtime_tree_empty_prefix() -> None:
    """Sadece 'ai.' olan boş anahtar reddedilmelidir."""
    with pytest.raises(ConfigFormatError, match="Önek sonrası anahtar adı boş olamaz"):
        extract_runtime_tree({"ai.": "value"})


def test_merge_property_sources_empty_list() -> None:
    """Boş kaynak listesi boş sözlük döndürmelidir."""
    assert merge_property_sources([]) == {}
    assert extract_runtime_tree({}) == {}


def test_merge_property_sources_invalid_format() -> None:
    """propertySources formatı geçersizse ConfigFormatError fırlatılmalıdır."""
    with pytest.raises(ConfigFormatError):
        merge_property_sources(["not-a-dict"])  # type: ignore[list-item]

    with pytest.raises(ConfigFormatError):
        merge_property_sources([{"name": "x", "source": "not-a-dict"}])
