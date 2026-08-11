from __future__ import annotations

from typing import Any

from services.parametros_zootecnicos import (
    PESO_BEZERRA_ARR,
    PESO_BOI_ARR,
    PESO_GARROTE_ARR,
    PESO_JOVEM_F_ARR,
    PESO_VACA_ARR,
)


def _lookup(mapping: dict[str, Any] | None, *keys: str) -> Any:
    if not mapping:
        return None
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _nested_lookup(production: dict[str, Any], *keys: str) -> Any:
    nested = production.get("sales") if isinstance(production.get("sales"), dict) else None
    if nested:
        value = _lookup(nested, *keys)
        if value is not None:
            return value
    return _lookup(production, *keys)


def _coerce_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _category_specs() -> tuple[dict[str, Any], ...]:
    return (
        {
            "name": "bois_vendidos",
            "price_keys": ("preco_boi_arr", "preco_boi", "preco_terminado_arr"),
            "weight_keys": ("peso_boi", "peso_boi_arr"),
            "default_weight": PESO_BOI_ARR,
            "unit": "arroba",
        },
        {
            "name": "matrizes_descartadas",
            "price_keys": ("preco_vaca_arr", "preco_vaca", "preco_descarte_vaca_arr"),
            "weight_keys": ("peso_vaca", "peso_vaca_arr"),
            "default_weight": PESO_VACA_ARR,
            "unit": "arroba",
        },
        {
            "name": "bezerras_vendidas",
            "price_keys": ("preco_bezerra_cab", "preco_bezerra"),
            "weight_keys": ("peso_bezerra", "peso_bezerra_arr"),
            "default_weight": PESO_BEZERRA_ARR,
            "unit": "cabeça",
        },
        {
            "name": "machos_vendidos",
            "price_keys": ("preco_bezerro_cab", "preco_bezerro"),
            "weight_keys": ("peso_bezerro", "peso_bezerro_arr"),
            "default_weight": None,
            "unit": "cabeça",
        },
        {
            "name": "femeas_vendidas",
            "price_keys": ("preco_novilha_arr", "preco_novilha", "preco_vaca_arr"),
            "weight_keys": ("peso_novilha", "peso_jovem_f", "peso_jovem_f_arr"),
            "default_weight": PESO_JOVEM_F_ARR,
            "unit": "arroba",
        },
        {
            "name": "garrotes_vendidos",
            "price_keys": ("preco_garrote_arr", "preco_garrote", "preco_boi_arr"),
            "weight_keys": ("peso_garrote", "peso_garrote_arr"),
            "default_weight": PESO_GARROTE_ARR,
            "unit": "arroba",
        },
    )


def calculate_revenues(production: dict[str, Any], prices: dict[str, Any]) -> dict[str, Any]:
    production = production or {}
    prices = prices or {}
    warnings: list[str] = []
    assumptions: list[str] = []
    valid = True

    receita_por_categoria: dict[str, float | None] = {}
    arrobas_vendidas = _coerce_float(
        _nested_lookup(production, "arrobas_vendidas", "arrobas_total_vendidas")
    )
    cabecas_vendidas = _coerce_float(
        _nested_lookup(production, "cabecas_vendidas", "vendidos", "total_vendido")
    )

    total_receita = 0.0
    total_heads = 0.0
    total_arrobas = 0.0

    for spec in _category_specs():
        qty = _coerce_float(_nested_lookup(production, spec["name"]))
        if qty is None:
            continue
        total_heads += max(qty, 0.0)
        if qty <= 0:
            receita_por_categoria[spec["name"]] = 0.0
            continue

        price = _coerce_float(_lookup(prices, *spec["price_keys"]))
        if price is None:
            warnings.append(
                f"missing price for {spec['name']} ({', '.join(spec['price_keys'])})"
            )
            receita_por_categoria[spec["name"]] = None
            valid = False
            continue

        weight = None
        if spec["unit"] == "arroba":
            weight = _coerce_float(_lookup(production, *spec["weight_keys"]))
            if weight is None:
                weight = spec["default_weight"]
                assumptions.append(
                    f"using default weight {weight} for {spec['name']}"
                )
            total_arrobas += qty * float(weight)
            receita = qty * float(weight) * price
        else:
            receita = qty * price

        receita_por_categoria[spec["name"]] = round(receita, 2)
        total_receita += receita

    if not valid:
        return {
            "valid": False,
            "warnings": warnings,
            "assumptions": assumptions,
            "receita_por_categoria": receita_por_categoria,
            "receita_total": None,
            "receita_por_cabeca": None,
            "receita_por_arroba": None,
            "cabecas_vendidas": cabecas_vendidas if cabecas_vendidas is not None else total_heads or None,
            "arrobas_vendidas": arrobas_vendidas,
        }

    if cabecas_vendidas is None:
        cabecas_vendidas = total_heads or None
    if arrobas_vendidas is None:
        arrobas_vendidas = total_arrobas or None

    receita_por_cabeca = None
    if cabecas_vendidas and cabecas_vendidas > 0:
        receita_por_cabeca = total_receita / cabecas_vendidas

    receita_por_arroba = None
    if arrobas_vendidas and arrobas_vendidas > 0:
        receita_por_arroba = total_receita / arrobas_vendidas

    return {
        "valid": True,
        "warnings": warnings,
        "assumptions": assumptions,
        "receita_por_categoria": receita_por_categoria,
        "receita_total": round(total_receita, 2),
        "receita_por_cabeca": round(receita_por_cabeca, 2) if receita_por_cabeca is not None else None,
        "receita_por_arroba": round(receita_por_arroba, 2) if receita_por_arroba is not None else None,
        "cabecas_vendidas": cabecas_vendidas,
        "arrobas_vendidas": round(arrobas_vendidas, 2) if arrobas_vendidas is not None else None,
    }
