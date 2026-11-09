from typing import Any

RUNTIME_PREFIX = "ai."


class ConfigFormatError(ValueError):
    """Config Server cevabı beklenen biçimde olmadığında fırlatılır."""


def merge_property_sources(sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Config Server propertySources listesini öncelik sırasına göre birleştirir.

    Config Server en yüksek öncelikli kaynağı listenin BAŞINA koyar.
    Baştakinin kazanması için kaynaklar sondan başa doğru uygulanır.
    """
    merged: dict[str, Any] = {}
    for item in reversed(sources):
        if not isinstance(item, dict) or "source" not in item:
            raise ConfigFormatError("propertySources elemanı 'source' sözlüğü içermelidir")
        source = item["source"]
        if not isinstance(source, dict):
            raise ConfigFormatError(f"Geçersiz source tipi: {type(source).__name__}")
        merged.update(source)
    return merged


def extract_runtime_tree(flat: dict[str, Any]) -> dict[str, Any]:
    """'ai.' önekli düzleştirilmiş anahtarları iç içe snake_case sözlüğe dönüştürür.

    Kurallar:
    - Sadece 'ai.' önekli anahtarlar işlenir, diğerleri elenir.
    - Kebab-case snake_case'e çevrilir ('max-steps' -> 'max_steps').
    - Çözülmemiş placeholder (${...}) veya liste anahtarları ([0]) varsa reddedilir.
    - Hata mesajlarında asla değer yazılmaz, sadece anahtar adı yer alır.
    """
    tree: dict[str, Any] = {}

    for key, value in flat.items():
        if not key.startswith(RUNTIME_PREFIX):
            continue

        stripped_key = key[len(RUNTIME_PREFIX) :]
        if not stripped_key:
            raise ConfigFormatError("Önek sonrası anahtar adı boş olamaz: 'ai.'")

        if "[" in stripped_key or "]" in stripped_key:
            raise ConfigFormatError(f"Liste anahtarları desteklenmiyor: {key}")

        if isinstance(value, str) and "${" in value:
            raise ConfigFormatError(f"Çözülmemiş placeholder tespit edildi: {key}")

        # Parçala ve kebab-case -> snake_case çevir
        raw_parts = stripped_key.split(".")
        parts = [p.replace("-", "_") for p in raw_parts]

        curr = tree
        for i, part in enumerate(parts[:-1]):
            if part in curr:
                if not isinstance(curr[part], dict):
                    conflict_path = ".".join(parts[: i + 1])
                    raise ConfigFormatError(
                        f"Çakışan konfigürasyon yolu (hem yaprak hem dal): {conflict_path}"
                    )
            else:
                curr[part] = {}
            curr = curr[part]

        leaf = parts[-1]
        if leaf in curr and isinstance(curr[leaf], dict):
            raise ConfigFormatError(
                f"Çakışan konfigürasyon yolu (hem yaprak hem dal): {'.'.join(parts)}"
            )
        curr[leaf] = value

    return tree
