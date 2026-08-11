"""Projeção mensal de caixa para análise de crédito.

Camada de compatibilidade sobre ``services.cashflow_engine``.
"""
from __future__ import annotations

from services.cashflow_engine import project_cashflow


def projetar_fluxo_mensal(anos: list[dict]) -> dict:
    result = project_cashflow(
        {"years": anos or []},
        {},
        horizon_months=12 * len(anos or []),
    )

    meses = []
    for row in result["months"]:
        saldo_livre = round(row["saldo_final"] - row["saldo_inicial"], 2)
        meses.append({
            "ano": row["ano"],
            "mes": row["mes"],
            "receita_estimada": round(row["entradas"], 2),
            "custo_operacional_estimado": round(row["custos_operacionais"], 2),
            "servico_divida": round(row["parcelas"] + row["juros"], 2),
            "fluxo_livre": saldo_livre,
            "saldo_acumulado": round(row["saldo_final"], 2),
            "estimated": row["estimated"],
            "warnings": list(row["warnings"]),
            "saldo_inicial": round(row["saldo_inicial"], 2),
            "entradas": round(row["entradas"], 2),
            "custos_operacionais": round(row["custos_operacionais"], 2),
            "investimentos": round(row["investimentos"], 2),
            "parcelas": round(row["parcelas"], 2),
            "juros": round(row["juros"], 2),
            "saldo_operacional": round(row["saldo_operacional"], 2),
            "saldo_final": round(row["saldo_final"], 2),
        })

    top_warning = (
        "Sem calendário mensal informado, a distribuição linear é estimada. "
        "Use dados mensais reais para decisão final."
    )
    if result.get("warnings"):
        top_warning = f"{top_warning} {'; '.join(result['warnings'])}"

    legacy_method = "distribuicao_linear_anual_estimada" if result.get("estimated") else result.get("method")
    return {
        "metodo": legacy_method,
        "meses": meses,
        "saldo_minimo": result.get("saldo_minimo", 0.0),
        "mes_critico": result.get("mes_critico"),
        "aviso": top_warning,
        "estimated": result.get("estimated", False),
        "warnings": list(result.get("warnings") or []),
        "months": result["months"],
    }
