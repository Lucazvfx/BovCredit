from __future__ import annotations

from typing import Any


def _coerce_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def calculate_economic_result(
    revenues: dict[str, Any],
    costs: dict[str, Any],
    inventory_change: float = 0,
) -> dict[str, Any]:
    revenues = revenues or {}
    costs = costs or {}
    warnings: list[str] = []
    assumptions: list[str] = []

    receita_total = _coerce_float(revenues.get("receita_total"))
    if receita_total is None:
        warnings.append("missing total revenue")
        receita_total = 0.0

    custo_operacional = _coerce_float(costs.get("custo_operacional"))
    custo_manutencao = _coerce_float(costs.get("custo_manutencao"))
    custo_reposicao = _coerce_float(costs.get("custo_reposicao"))
    reposicao_reprodutores = _coerce_float(costs.get("reposicao_reprodutores"))
    servico_divida_anual = _coerce_float(costs.get("servico_divida_anual"))
    custo_investimento = _coerce_float(costs.get("custo_investimento"))

    if custo_operacional is None:
        if custo_manutencao is not None or custo_reposicao is not None:
            if custo_manutencao is None:
                custo_manutencao = 0.0
                assumptions.append("missing maintenance cost assumed zero")
            if custo_reposicao is None:
                custo_reposicao = 0.0
                assumptions.append("missing replacement cost assumed zero")
            custo_operacional = custo_manutencao + custo_reposicao
            assumptions.append("operational cost reconstructed from maintenance + replacement")
        else:
            warnings.append("missing operational cost")
            custo_operacional = 0.0

    if custo_manutencao is None:
        custo_manutencao = 0.0
        assumptions.append("missing maintenance cost assumed zero")
    if custo_reposicao is None:
        custo_reposicao = max(custo_operacional - custo_manutencao, 0.0)
        assumptions.append("replacement cost inferred from operational cost")
    if reposicao_reprodutores is None:
        reposicao_reprodutores = 0.0
    if servico_divida_anual is None:
        servico_divida_anual = 0.0
    if custo_investimento is None:
        custo_investimento = 0.0

    margem_bruta = receita_total - custo_operacional
    resultado_operacional = margem_bruta - reposicao_reprodutores
    resultado_economico = resultado_operacional + float(inventory_change or 0.0)
    fluxo_livre = (
        resultado_operacional - servico_divida_anual
        if servico_divida_anual > 0
        else None
    )
    dscr_operacional = (
        round(resultado_operacional / servico_divida_anual, 2)
        if servico_divida_anual > 0
        else None
    )

    cabecas = _coerce_float(costs.get("cabecas"))
    arrobas_vendidas = _coerce_float(costs.get("arrobas_vendidas"))

    preco_breakeven = None
    preco_breakeven_unidade = None
    if arrobas_vendidas and arrobas_vendidas > 0:
        preco_breakeven = custo_operacional / arrobas_vendidas
        preco_breakeven_unidade = "R$/arroba"
    elif cabecas and cabecas > 0:
        preco_breakeven = custo_operacional / cabecas
        preco_breakeven_unidade = "R$/cabeça"

    custo_por_cabeca = (
        custo_operacional / cabecas if cabecas and cabecas > 0 else None
    )
    custo_por_arroba = (
        custo_operacional / arrobas_vendidas if arrobas_vendidas and arrobas_vendidas > 0 else None
    )
    receita_por_cabeca = (
        receita_total / cabecas if cabecas and cabecas > 0 else None
    )
    receita_por_arroba = (
        receita_total / arrobas_vendidas if arrobas_vendidas and arrobas_vendidas > 0 else None
    )

    valor_rebanho_ini = _coerce_float(costs.get("valor_rebanho_ini"))
    valor_rebanho_fim = _coerce_float(costs.get("valor_rebanho_fim"))
    if valor_rebanho_ini is None and valor_rebanho_fim is None:
        valor_rebanho_ini = 0.0
        valor_rebanho_fim = float(inventory_change or 0.0)
    elif valor_rebanho_ini is None:
        valor_rebanho_ini = float(valor_rebanho_fim or 0.0) - float(inventory_change or 0.0)
    elif valor_rebanho_fim is None:
        valor_rebanho_fim = float(valor_rebanho_ini or 0.0) + float(inventory_change or 0.0)

    return {
        "valid": not warnings,
        "warnings": warnings,
        "assumptions": assumptions,
        "receita_total": round(receita_total, 2),
        "receita_vendas": round(receita_total, 2),
        "custo_manutencao": round(custo_manutencao, 2),
        "custo_reposicao": round(custo_reposicao, 2),
        "custo_investimento": round(custo_investimento, 2),
        "reposicao_reprodutores": round(reposicao_reprodutores, 2),
        "servico_divida_anual": round(servico_divida_anual, 2),
        "custo_operacional": round(custo_operacional, 2),
        "margem_bruta": round(margem_bruta, 2),
        "resultado_operacional": round(resultado_operacional, 2),
        "resultado_economico": round(resultado_economico, 2),
        "resultado_antes_reposicao": round(receita_total - custo_manutencao, 2),
        "variacao_estoque": round(float(inventory_change or 0.0), 2),
        "valor_rebanho_ini": round(valor_rebanho_ini, 2),
        "valor_rebanho_fim": round(valor_rebanho_fim, 2),
        "fluxo_livre": round(fluxo_livre, 2) if fluxo_livre is not None else None,
        "dscr_operacional": dscr_operacional,
        "preco_breakeven": round(preco_breakeven, 2) if preco_breakeven is not None else None,
        "preco_breakeven_unidade": preco_breakeven_unidade,
        "custo_por_cabeca": round(custo_por_cabeca, 2) if custo_por_cabeca is not None else None,
        "custo_por_arroba": round(custo_por_arroba, 2) if custo_por_arroba is not None else None,
        "receita_por_cabeca": round(receita_por_cabeca, 2) if receita_por_cabeca is not None else None,
        "receita_por_arroba": round(receita_por_arroba, 2) if receita_por_arroba is not None else None,
    }
