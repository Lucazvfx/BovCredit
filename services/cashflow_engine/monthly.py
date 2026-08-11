from __future__ import annotations

from typing import Any

from services.cashflow_engine.models import CashflowMonth, CashflowProjection
from services.cashflow_engine.seasonality import distribute_amount, resolve_month_weights


def _coerce_float(value: Any, default: float = 0.0) -> float:
    if value is None or isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_year_rows(annual_projection: dict | None, horizon_months: int) -> list[dict]:
    annual_projection = annual_projection or {}
    rows = annual_projection.get("years")
    if rows is None:
        rows = annual_projection.get("anos")
    if rows is None:
        rows = annual_projection.get("rows")
    if rows is None:
        rows = [annual_projection]
    if not isinstance(rows, list):
        rows = list(rows)
    if not rows:
        rows = [{}]
    horizon_years = max(1, -(-horizon_months // 12))
    return [dict(rows[min(index, len(rows) - 1)]) for index in range(horizon_years)]


def _category_amounts(year_row: dict) -> dict[str, float] | None:
    detailed_keys = {"calf_sales", "finished_sales", "purchases", "costs", "investments"}
    if not any(key in year_row for key in detailed_keys):
        return None
    return {
        "calf_sales": _coerce_float(year_row.get("calf_sales")),
        "finished_sales": _coerce_float(year_row.get("finished_sales")),
        "purchases": _coerce_float(year_row.get("purchases")),
        "costs": _coerce_float(year_row.get("costs")),
        "investments": _coerce_float(year_row.get("investments")),
    }


def _needs_category_distribution(
    category: str,
    amount: float,
    calendar: dict | None,
    seasonality: dict | None,
) -> bool:
    if abs(amount) > 0:
        return True
    calendar = calendar or {}
    seasonality = seasonality or {}
    return category in calendar or category in seasonality


def _generic_amounts(year_row: dict) -> dict[str, float]:
    entradas = year_row.get("entradas")
    if entradas is None:
        entradas = year_row.get("receita")
    if entradas is None:
        entradas = year_row.get("receita_total")

    custos = year_row.get("custos_operacionais")
    if custos is None:
        custos = year_row.get("custo")

    investimentos = year_row.get("investimentos")
    if investimentos is None:
        investimentos = year_row.get("investimento")

    parcelas = year_row.get("parcelas")
    if parcelas is None:
        parcelas = year_row.get("principal")

    juros = year_row.get("juros")
    if juros is None:
        juros = year_row.get("juros_anual")

    service = year_row.get("servico_divida_anual")
    if service is None:
        service = year_row.get("debt_service")

    return {
        "entradas": _coerce_float(entradas),
        "custos_operacionais": _coerce_float(custos),
        "investimentos": _coerce_float(investimentos),
        "parcelas": _coerce_float(parcelas),
        "juros": _coerce_float(juros),
        "servico_divida_anual": _coerce_float(service),
    }


def _year_label(year_row: dict, fallback: int) -> int:
    label = year_row.get("ano")
    if label is None or isinstance(label, bool):
        return fallback
    try:
        return int(label)
    except (TypeError, ValueError):
        return fallback


def _split_loan_schedule(
    debt_schedule: dict | None,
    horizon_months: int,
) -> list[tuple[float, float]]:
    debt_schedule = debt_schedule or {}
    credito_valor = _coerce_float(debt_schedule.get("credito_valor"), default=0.0)
    juros_aa = _coerce_float(debt_schedule.get("juros_aa"), default=0.0)
    prazo_meses = int(debt_schedule.get("prazo_meses") or horizon_months or 0)
    carencia_meses = int(debt_schedule.get("carencia_meses") or 0)

    if credito_valor <= 0 or juros_aa < 0 or prazo_meses <= 0:
        return []

    from services.parecer_credito import parcela_price, principal_apos_carencia

    i = (1 + juros_aa) ** (1 / 12) - 1
    n_amort = max(prazo_meses - carencia_meses, 0)
    if n_amort <= 0:
        return [(0.0, 0.0) for _ in range(horizon_months)]

    principal_amortizado = principal_apos_carencia(credito_valor, juros_aa, carencia_meses)
    parcela_mensal = parcela_price(principal_amortizado, juros_aa, n_amort)

    rows: list[tuple[float, float]] = []
    saldo = credito_valor
    for month in range(1, horizon_months + 1):
        if month <= carencia_meses:
            rows.append((0.0, 0.0))
            saldo *= (1 + i)
            continue
        if month > prazo_meses:
            rows.append((0.0, 0.0))
            continue
        juros = round(saldo * i, 2)
        principal = round(max(parcela_mensal - juros, 0.0), 2)
        if month == prazo_meses:
            principal = round(saldo, 2)
            juros = round(max(parcela_mensal - principal, 0.0), 2)
        rows.append((principal, juros))
        saldo = max(saldo - principal, 0.0)
    return rows


def _expand_generic_service(year_row: dict) -> list[tuple[float, float]]:
    generic = _generic_amounts(year_row)
    parcelas_anuais = generic["parcelas"]
    juros_anuais = generic["juros"]
    servico = generic["servico_divida_anual"]

    if parcelas_anuais or juros_anuais:
        parcelas = [round(parcelas_anuais / 12.0, 2)] * 12
        juros = [round(juros_anuais / 12.0, 2)] * 12
        parcelas[-1] = round(parcelas_anuais - sum(parcelas[:-1]), 2)
        juros[-1] = round(juros_anuais - sum(juros[:-1]), 2)
        return list(zip(parcelas, juros))

    if servico:
        parcelas = [round(servico / 12.0, 2)] * 12
        parcelas[-1] = round(servico - sum(parcelas[:-1]), 2)
        return [(value, 0.0) for value in parcelas]

    return [(0.0, 0.0)] * 12


def project_cashflow(
    annual_projection: dict,
    debt_schedule: dict,
    *,
    horizon_months: int,
    calendar: dict | None = None,
    seasonality: dict | None = None,
) -> dict:
    horizon_months = int(horizon_months or 0)
    if horizon_months <= 0:
        return {
            "months": [],
            "estimated": True,
            "warnings": ["horizon_months must be positive"],
            "saldo_minimo": 0.0,
            "mes_critico": None,
            "method": "empty",
        }

    year_rows = _as_year_rows(annual_projection, horizon_months)
    loan_schedule = _split_loan_schedule(debt_schedule, horizon_months)

    months: list[CashflowMonth] = []
    saldo = 0.0
    top_warnings: list[str] = []

    for month_index in range(horizon_months):
        year_index = min(month_index // 12, len(year_rows) - 1)
        month_in_year = month_index % 12
        year_row = year_rows[year_index]
        year_label = _year_label(year_row, year_index + 1)

        detailed = _category_amounts(year_row)
        row_warnings: list[str] = []
        row_estimated = False

        if detailed is not None:
            calf_amount = detailed["calf_sales"]
            finished_amount = detailed["finished_sales"]
            purchase_amount = detailed["purchases"]
            cost_amount = detailed["costs"]
            invest_amount = detailed["investments"]

            calf_weights, calf_est, calf_warn = (([1.0 / 12.0] * 12, False, [])
                if not _needs_category_distribution("calf_sales", calf_amount, calendar, seasonality)
                else resolve_month_weights("calf_sales", calendar, seasonality))
            finished_weights, fin_est, fin_warn = (([1.0 / 12.0] * 12, False, [])
                if not _needs_category_distribution("finished_sales", finished_amount, calendar, seasonality)
                else resolve_month_weights("finished_sales", calendar, seasonality))
            purchase_weights, purchase_est, purchase_warn = (([1.0 / 12.0] * 12, False, [])
                if not _needs_category_distribution("purchases", purchase_amount, calendar, seasonality)
                else resolve_month_weights("purchases", calendar, seasonality))
            cost_weights, cost_est, cost_warn = (([1.0 / 12.0] * 12, False, [])
                if not _needs_category_distribution("costs", cost_amount, calendar, seasonality)
                else resolve_month_weights("costs", calendar, seasonality))
            invest_weights, invest_est, invest_warn = (([1.0 / 12.0] * 12, False, [])
                if not _needs_category_distribution("investments", invest_amount, calendar, seasonality)
                else resolve_month_weights("investments", calendar, seasonality))
            row_estimated = any((calf_est, fin_est, purchase_est, cost_est, invest_est))
            row_warnings.extend(calf_warn + fin_warn + purchase_warn + cost_warn + invest_warn)

            calf_monthly = distribute_amount(calf_amount, calf_weights)[month_in_year]
            finished_monthly = distribute_amount(finished_amount, finished_weights)[month_in_year]
            purchase_monthly = distribute_amount(purchase_amount, purchase_weights)[month_in_year]
            cost_monthly = distribute_amount(cost_amount, cost_weights)[month_in_year]
            invest_monthly = distribute_amount(invest_amount, invest_weights)[month_in_year]
            entradas = calf_monthly + finished_monthly
            custos_operacionais = cost_monthly
            investimentos = purchase_monthly + invest_monthly
        else:
            generic = _generic_amounts(year_row)
            entradas_weights, entradas_est, entradas_warn = resolve_month_weights("entradas", calendar, seasonality)
            custos_weights, custos_est, custos_warn = resolve_month_weights("custos_operacionais", calendar, seasonality)
            invest_weights, invest_est, invest_warn = resolve_month_weights("investimentos", calendar, seasonality)
            row_estimated = any((entradas_est, custos_est, invest_est))
            row_warnings.extend(entradas_warn + custos_warn + invest_warn)

            entradas = distribute_amount(generic["entradas"], entradas_weights)[month_in_year]
            custos_operacionais = distribute_amount(generic["custos_operacionais"], custos_weights)[month_in_year]
            investimentos = distribute_amount(generic["investimentos"], invest_weights)[month_in_year]

        if loan_schedule:
            parcelas, juros = loan_schedule[month_index]
        else:
            parcelas, juros = _expand_generic_service(year_row)[month_in_year]

        saldo_inicial = saldo
        saldo_operacional = round(entradas - custos_operacionais - investimentos, 2)
        saldo_final = round(saldo_inicial + saldo_operacional - parcelas - juros, 2)
        saldo = saldo_final

        if row_estimated:
            row_warnings.append("monthly values estimated from linear fallback")
        row_warnings = [warning for warning in dict.fromkeys(row_warnings) if warning]
        top_warnings.extend(row_warnings)

        months.append(
            CashflowMonth(
                ano=year_label,
                mes=month_in_year + 1,
                saldo_inicial=round(saldo_inicial, 2),
                entradas=round(entradas, 2),
                custos_operacionais=round(custos_operacionais, 2),
                investimentos=round(investimentos, 2),
                parcelas=round(parcelas, 2),
                juros=round(juros, 2),
                saldo_operacional=saldo_operacional,
                saldo_final=saldo_final,
                estimated=row_estimated,
                warnings=tuple(row_warnings),
            )
        )

    saldo_minimo = min((month.saldo_final for month in months), default=0.0)
    mes_critico = None
    if months:
        critico = min(months, key=lambda month: month.saldo_final)
        mes_critico = {"ano": critico.ano, "mes": critico.mes}

    estimated = any(month.estimated for month in months)
    warnings = tuple(dict.fromkeys(top_warnings))
    method = "monthly_cashflow_estimated" if estimated else "monthly_cashflow_seasonal"

    projection = CashflowProjection(
        months=tuple(months),
        estimated=estimated,
        warnings=warnings,
        saldo_minimo=round(saldo_minimo, 2),
        mes_critico=mes_critico,
        method=method,
    )
    return projection.to_dict()
