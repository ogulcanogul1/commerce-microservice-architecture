from typing import Any


def flatten_paths(tree: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """İç içe sözlüğü nokta notasyonlu düz sözlüğe çevirir.

    Örnek:
        {"agent": {"max_steps": 4}} -> {"agent.max_steps": 4}
    """
    result: dict[str, Any] = {}
    for key, val in tree.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(val, dict):
            result.update(flatten_paths(val, prefix=path))
        else:
            result[path] = val
    return result


def get_path(tree: dict[str, Any], path: str) -> Any:
    """Nokta notasyonlu yoldan değeri okur. Bulamazsa KeyError fırlatır."""
    parts = path.split(".")
    curr: Any = tree
    for part in parts:
        if not isinstance(curr, dict) or part not in curr:
            raise KeyError(f"Geçersiz yol: {path}")
        curr = curr[part]
    return curr


def set_path(tree: dict[str, Any], path: str, value: Any) -> None:
    """Nokta notasyonlu yola değer yazar. Gerekli ara sözlükleri oluşturur."""
    parts = path.split(".")
    curr = tree
    for part in parts[:-1]:
        if part not in curr or not isinstance(curr[part], dict):
            curr[part] = {}
        curr = curr[part]
    curr[parts[-1]] = value
