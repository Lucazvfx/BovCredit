"""Motor puro de stress scenarios.

O objetivo aqui é manter as variações explícitas, determinísticas e fáceis de
auditar: cada cenário informa o que mudou, o DSCR final e se a análise ficou
sem cobertura.
"""
from __future__ import annotations

from copy import deepcopy
from statistics import mean
from typing import Any


def _coerce_float(value: Any, default: float = 0.0) -> float:
    if value is None or isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _year_rows(base_analysis: dict | None) -> list[dict]:
    base_analysis = base_analysis or {}
    rows = (
        base_analysis.get("projecao_anos")
        or base_analysis.get("analysis", {}).get("periods")
        or base_analysis.get("periods")
        or []
    )
    if not isinstance(rows, list):
        rows = list(rows)
    cleaned = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            row = {}
        cleaned.append(dict(row, ano=int(row.get("ano") or index)))
    if not cleaned:
        cleaned = [{"ano": 1, "receita": 0.0, "custo": 0.0, "resultado": 0.0, "dscr": None}]
    return cleaned


def _service_from_base(base_analysis: dict, rows: list[dict]) -> float:
    for key in ("servico_divida_anual", "servico_divida_total_anual", "debt_service"):
        value = _coerce_float(base_analysis.get(key))
        if value > 0:
            return value
    analysis = base_analysis.get("analysis")
    if isinstance(analysis, dict):
        for key in ("servico_divida_anual", "servico_divida_total_anual"):
            value = _coerce_float(analysis.get(key))
            if value > 0:
                return value
    for row in rows:
        value = _coerce_float(row.get("servico_divida_anual"))
        if value > 0:
            return value
    return 0.0


def _row_service(row: dict, fallback: float) -> float:
    for key in ("servico_divida_anual", "servico_divida_total_anual", "debt_service"):
        if key in row:
            return _coerce_float(row.get(key))
    return fallback


def _apply_multiplier(value: float, pct: float | None, *, invert: bool = False) -> float:
    if pct is None:
        return value
    factor = 1 + (pct / 100.0)
    if invert:
        factor = 1 - (pct / 100.0)
    return value * max(factor, 0.0)


def _scenario_changes(scenario: dict) -> list[str]:
    changes: list[str] = []
    for key in (
        "price_pct",
        "revenue_pct",
        "cost_pct",
        "natality_pct",
        "mortality_pct",
        "gmd_pct",
        "commercialization_delay_months",
    ):
        if key not in scenario or scenario[key] in (None, 0, 0.0):
            continue
        value = scenario[key]
        if key == "commercialization_delay_months":
            sign = "+" if float(value) >= 0 else ""
            changes.append(f"{key} {sign}{int(value)}m")
            continue
        sign = "+" if float(value) > 0 else ""
        changes.append(f"{key} {sign}{float(value):g}%")
    return changes


def _stress_multiplier(scenario: dict) -> tuple[float, float]:
    revenue_multiplier = 1.0
    cost_multiplier = 1.0

    price_pct = scenario.get("price_pct")
    # Choque de QUANTIDADE, independente de preço: quebra de safra na lavoura,
    # perda de produção. Na pecuária o mesmo efeito chega por natalidade e
    # mortalidade; a lavoura não tem esses caminhos e precisava de um direto.
    revenue_pct = scenario.get("revenue_pct")
    natality_pct = scenario.get("natality_pct")
    mortality_pct = scenario.get("mortality_pct")
    gmd_pct = scenario.get("gmd_pct")
    delay_months = _coerce_float(scenario.get("commercialization_delay_months"))
    cost_pct = scenario.get("cost_pct")

    revenue_multiplier = _apply_multiplier(revenue_multiplier, price_pct)
    revenue_multiplier = _apply_multiplier(revenue_multiplier, revenue_pct)
    revenue_multiplier = _apply_multiplier(revenue_multiplier, natality_pct)
    if mortality_pct is not None:
        revenue_multiplier *= max(1 - (_coerce_float(mortality_pct) / 100.0), 0.0)
    revenue_multiplier = _apply_multiplier(revenue_multiplier, gmd_pct)
    if delay_months:
        revenue_multiplier *= max(1 - (delay_months / 12.0), 0.0)

    cost_multiplier = _apply_multiplier(cost_multiplier, cost_pct)
    return revenue_multiplier, cost_multiplier


def _pick_period(periods: list[dict], *, highest: bool) -> dict | None:
    available = [period for period in periods if period.get("dscr") is not None]
    if not available:
        return None
    picked = max(available, key=lambda item: item["dscr"]) if highest else min(available, key=lambda item: item["dscr"])
    return {
        "ano": picked["ano"],
        "dscr": picked["dscr"],
        "resultado": picked["resultado"],
        "servico_divida_anual": picked["servico_divida_anual"],
        "uncovered": picked["uncovered"],
    }


def default_stress_scenarios() -> list[dict]:
    return [
        {"nome": "queda_preco", "price_pct": -15},
        {"nome": "custo_alto", "cost_pct": 15},
        {"nome": "natalidade_baixa", "natality_pct": -10},
        {"nome": "mortalidade_alta", "mortality_pct": 8},
        {"nome": "gmd_baixo", "gmd_pct": -12},
        {"nome": "comercializacao_atrasada", "commercialization_delay_months": 3},
        {
            "nome": "choque_combinado",
            "price_pct": -15,
            "cost_pct": 10,
            "natality_pct": -8,
            "mortality_pct": 5,
            "gmd_pct": -10,
            "commercialization_delay_months": 3,
        },
    ]


def run_stress_tests(base_analysis: dict, scenarios: list[dict] | None) -> dict:
    base_snapshot = deepcopy(base_analysis or {})
    rows = _year_rows(base_snapshot)
    service_divida = _service_from_base(base_snapshot, rows)
    scenarios = list(scenarios or default_stress_scenarios())

    scenario_results = []
    for scenario in scenarios:
        scenario = deepcopy(scenario or {})
        revenue_multiplier, cost_multiplier = _stress_multiplier(scenario)
        applied_changes = _scenario_changes(scenario)

        stressed_rows = []
        dscrs = []
        for row in rows:
            receita_base = _coerce_float(row.get("receita"), _coerce_float(row.get("resultado")))
            custo_base = _coerce_float(row.get("custo"))
            resultado_base = _coerce_float(row.get("resultado"), receita_base - custo_base)
            service_row = _row_service(row, service_divida)

            if receita_base or custo_base:
                receita = round(receita_base * revenue_multiplier, 2)
                custo = round(custo_base * cost_multiplier, 2)
                resultado = round(receita - custo, 2)
            else:
                resultado = round(resultado_base * revenue_multiplier - (resultado_base * (cost_multiplier - 1)), 2)
                receita = round(_coerce_float(row.get("receita"), resultado), 2)
                custo = round(_coerce_float(row.get("custo"), 0.0) * cost_multiplier, 2)

            dscr = round(resultado / service_row, 2) if service_row > 0 else None
            stressed_rows.append(
                {
                    **row,
                    "receita": receita,
                    "custo": custo,
                    "resultado": resultado,
                    "servico_divida_anual": service_row,
                    "dscr": dscr,
                    "uncovered": dscr is not None and dscr < 1.0,
                }
            )
            if dscr is not None:
                dscrs.append(dscr)

        dscr_minimo = round(min(dscrs), 2) if dscrs else None
        dscr_medio = round(mean(dscrs), 2) if dscrs else None
        pior_periodo = _pick_period(stressed_rows, highest=False)
        melhor_periodo = _pick_period(stressed_rows, highest=True)
        uncovered_periods = [row["ano"] for row in stressed_rows if row.get("uncovered")]
        uncovered = bool(uncovered_periods) or (dscr_minimo is not None and dscr_minimo < 1.0)

        stressed_analysis = deepcopy(base_snapshot)
        stressed_analysis["base_analysis"] = base_snapshot
        stressed_analysis["projecao_anos"] = stressed_rows
        stressed_analysis["stress"] = {
            "nome": scenario.get("nome"),
            "applied_changes": applied_changes,
            "uncovered_periods": uncovered_periods,
        }
        conclusao = dict(stressed_analysis.get("conclusao") or {})
        if dscr_minimo is not None:
            conclusao.update(
                {
                    "dscr_minimo": dscr_minimo,
                    "dscr_medio": dscr_medio,
                    "ano_critico": pior_periodo["ano"] if pior_periodo else conclusao.get("ano_critico"),
                    "recomendacao": (
                        "aprovar"
                        if dscr_minimo >= 1.30
                        else "ressalva"
                        if dscr_minimo >= 1.00
                        else "negar"
                    ),
                }
            )
        stressed_analysis["conclusao"] = conclusao
        stressed_analysis["dscr_minimo"] = dscr_minimo
        stressed_analysis["dscr_medio"] = dscr_medio
        stressed_analysis["pior_periodo"] = pior_periodo
        stressed_analysis["melhor_periodo"] = melhor_periodo
        stressed_analysis["uncovered_periods"] = uncovered_periods
        stressed_analysis["uncovered"] = uncovered

        scenario_results.append(
            {
                "nome": scenario.get("nome"),
                "applied_changes": applied_changes,
                "base_analysis": base_snapshot,
                "analysis": stressed_analysis,
                "dscr_minimo": dscr_minimo,
                "dscr_medio": dscr_medio,
                "pior_periodo": pior_periodo,
                "melhor_periodo": melhor_periodo,
                "uncovered_periods": uncovered_periods,
                "uncovered": uncovered,
            }
        )

    return {
        "base_analysis": base_snapshot,
        "scenarios": scenario_results,
    }
