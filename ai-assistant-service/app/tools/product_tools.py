from typing import Any

from app.core.config import settings
from app.core.exceptions import BusinessRuleException
from app.tools import base_tool
from app.tools.base_tool import tool_registry


@tool_registry.register(
    name="search_catalog_products",
    description=(
        "Scenario C.1: Searches the product catalog in product-service and checks stock availability "
        "in inventory-service by keywords, category, or product attributes (e.g. pet-friendly, low-light)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search keywords or attribute requirements (e.g. 'kedi dostu az ışık bitki', 'macbook')",
            },
            "check_stock": {
                "type": "boolean",
                "description": "Whether to enrich results with live stock from inventory-service",
            },
        },
        "required": ["query"],
    },
)
async def search_catalog_products(query: str, check_stock: bool = True) -> dict[str, Any]:
    page_data = await base_tool.http_client.get(
        f"{settings.PRODUCT_SERVICE_URL}/api/v1/products",
        params={"page": 0, "size": 50},
    )
    products: list[dict[str, Any]] = (
        page_data.get("content", []) if isinstance(page_data, dict) else []
    )

    terms = [t.lower() for t in query.strip().split() if len(t) > 1]
    scored_matches: list[tuple[int, dict[str, Any]]] = []

    for prod in products:
        searchable_blob = " ".join(
            [
                str(prod.get("name", "")),
                str(prod.get("description", "")),
                str(prod.get("categoryName", "")),
                " ".join(f"{k}:{v}" for k, v in (prod.get("attributes") or {}).items()),
            ]
        ).lower()
        score = sum(1 for term in terms if term in searchable_blob)
        if score > 0 or not terms:
            scored_matches.append((score, prod))

    scored_matches.sort(key=lambda item: item[0], reverse=True)
    matched_products = [prod for _, prod in scored_matches[:10]]

    if check_stock:
        for prod in matched_products:
            sku = prod.get("sku")
            if sku:
                try:
                    inv = await base_tool.http_client.get(
                        f"{settings.INVENTORY_SERVICE_URL}/api/v1/inventory/{sku}"
                    )
                    prod["availableQuantity"] = inv.get("availableQuantity", 0)
                except Exception:
                    prod["availableQuantity"] = None

    return {
        "query": query,
        "matchCount": len(matched_products),
        "products": matched_products,
    }


@tool_registry.register(
    name="check_hardware_compatibility",
    description=(
        "Scenario C.2: Validates technical compatibility between hardware components in the customer's cart "
        "(e.g. Motherboard socket LGA1700/AM5 vs CPU socket, and Motherboard RAM generation DDR4/DDR5 vs RAM module)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "skus": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of product SKUs to verify for hardware compatibility",
            }
        },
        "required": ["skus"],
    },
)
async def check_hardware_compatibility(skus: list[str]) -> dict[str, Any]:
    if not skus or len(skus) < 2:
        raise BusinessRuleException("At least 2 product SKUs are required to check hardware compatibility")

    products: list[dict[str, Any]] = []
    for sku in skus:
        prod = await base_tool.http_client.get(
            f"{settings.PRODUCT_SERVICE_URL}/api/v1/products/sku/{sku.strip()}"
        )
        products.append(prod)

    sockets: dict[str, str] = {}
    ram_types: dict[str, str] = {}

    for prod in products:
        sku = prod.get("sku", "UNKNOWN")
        attrs: dict[str, str] = {
            str(k).lower(): str(v).upper() for k, v in (prod.get("attributes") or {}).items()
        }
        if "socket" in attrs:
            sockets[sku] = attrs["socket"]
        if "ram_type" in attrs or "memory_type" in attrs:
            ram_types[sku] = attrs.get("ram_type") or attrs.get("memory_type", "")

    issues: list[str] = []

    unique_sockets = set(sockets.values())
    if len(unique_sockets) > 1:
        details = ", ".join(f"{k}={v}" for k, v in sockets.items())
        issues.append(f"İşlemci ve Anakart soket uyuşmazlığı tespit edildi ({details}).")

    unique_ram = set(ram_types.values())
    if len(unique_ram) > 1:
        details = ", ".join(f"{k}={v}" for k, v in ram_types.items())
        issues.append(f"Anakart ve RAM bellek nesli uyuşmazlığı tespit edildi ({details}).")

    compatible = len(issues) == 0
    return {
        "compatible": compatible,
        "checkedProducts": [
            {
                "sku": p.get("sku"),
                "name": p.get("name"),
                "attributes": p.get("attributes", {}),
            }
            for p in products
        ],
        "incompatibilityIssues": issues,
        "message": (
            "Seçtiğiniz tüm donanım parçaları birbiriyle tam uyumludur."
            if compatible
            else "Dikkat! Sepetinizdeki parçalarda donanım uyumsuzluğu bulundu: " + " ".join(issues)
        ),
    }
