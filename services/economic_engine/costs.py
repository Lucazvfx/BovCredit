from __future__ import annotations

from typing import Any


def _lookup(mapping: dict[str, Any] | None, *keys: str) -> Any:
    if not mapping:
        return None
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _coerce_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def calculate_costs(production: dict[str, Any], cost_parameters: dict[str, Any]) -> dict[str, Any]:
    production = production or {}
    cost_parameters = cost_parameters or {}
    warnings: list[str] = []
    assumptions: list[str] = []
    valid = True

    fixed = _coerce_float(_lookup(cost_parameters, "custo_fixo_operacional", "fixed_operating_cost"))
    variable = _coerce_float(_lookup(cost_parameters, "custo_variavel_operacional", "variable_operating_cost"))
    maintenance = _coerce_float(_lookup(cost_parameters, "custo_manutencao", "maintenance_cost"))

    if maintenance is None:
        if fixed is None and variable is None:
            warnings.append("missing operating maintenance cost")
            valid = False
            maintenance = None
        else:
            maintenance = (fixed or 0.0) + (variable or 0.0)
    else:
        if fixed is None and variable is None:
            assumptions.append("maintenance cost supplied directly")
        elif fixed is not None or variable is not None:
            expected = (fixed or 0.0) + (variable or 0.0)
            if abs(expected - maintenance) > 0.01:
                warnings.append(
                    "maintenance cost does not match fixed + variable operating cost"
                )
                valid = False

    replacement = _coerce_float(_lookup(cost_parameters, "custo_reposicao", "replacement_cost"))
    if replacement is None:
        replacement = 0.0
        assumptions.append("missing replacement cost assumed zero")

    investment = _coerce_float(_lookup(cost_parameters, "custo_investimento", "investment_cost"))
    if investment is None:
        investment = 0.0

    reposicao_reprodutores = _coerce_float(
        _lookup(cost_parameters, "reposicao_reprodutores", "breeding_replacement_cost")
    )
    if reposicao_reprodutores is None:
        reposicao_reprodutores = 0.0

    servico_divida_anual = _coerce_float(
        _lookup(cost_parameters, "servico_divida_anual", "debt_service")
    )
    if servico_divida_anual is None:
        servico_divida_anual = 0.0

    cabecas = _coerce_float(_lookup(production, "cabecas", "cabecas_vendidas", "headcount"))
    arrobas_vendidas = _coerce_float(_lookup(production, "arrobas_vendidas", "arrobas_total_vendidas"))

    custo_operacional = None if maintenance is None else maintenance + replacement
    custo_total = None
    if custo_operacional is not None:
        custo_total = custo_operacional + investment + reposicao_reprodutores + servico_divida_anual

    custo_por_cabeca = None
    if custo_operacional is not None and cabecas and cabecas > 0:
        custo_por_cabeca = custo_operacional / cabecas

    custo_por_arroba = None
    if custo_operacional is not None and arrobas_vendidas and arrobas_vendidas > 0:
        custo_por_arroba = custo_operacional / arrobas_vendidas

    return {
        "valid": valid and custo_operacional is not None,
        "warnings": warnings,
        "assumptions": assumptions,
        "custo_fixo_operacional": round(fixed, 2) if fixed is not None else None,
        "custo_variavel_operacional": round(variable, 2) if variable is not None else None,
        "custo_manutencao": round(maintenance, 2) if maintenance is not None else None,
        "custo_reposicao": round(replacement, 2),
        "custo_investimento": round(investment, 2),
        "reposicao_reprodutores": round(reposicao_reprodutores, 2),
        "servico_divida_anual": round(servico_divida_anual, 2),
        "custo_operacional": round(custo_operacional, 2) if custo_operacional is not None else None,
        "custo_total": round(custo_total, 2) if custo_total is not None else None,
        "cabecas": cabecas,
        "arrobas_vendidas": arrobas_vendidas,
        "custo_por_cabeca": round(custo_por_cabeca, 2) if custo_por_cabeca is not None else None,
        "custo_por_arroba": round(custo_por_arroba, 2) if custo_por_arroba is not None else None,
    }
