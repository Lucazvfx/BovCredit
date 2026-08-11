"""Motor puro de capacidade de pagamento e DSCR.

O módulo concentra a matemática de Price, carência capitalizada e leitura do
fluxo anual para suportar o novo engine independente.
"""
from __future__ import annotations

import os
from copy import deepcopy
from statistics import mean
from typing import Any

from services.proveniencia import (
    catalogo,
    do_modulo,
    politica,
    resumo as _resumo_prov,
)


DSCR_APROVAR = politica(
    1.30,
    "Política de crédito da instituição",
    rotulo="DSCR para aprovar",
    nota="Cobertura mínima do serviço da dívida no ano crítico do prazo.",
)
DSCR_RESSALVA = politica(
    1.00,
    "Política de crédito da instituição",
    rotulo="DSCR para ressalva",
)

_CARENCIA_SEM_CAP = os.environ.get("CARENCIA_SEM_CAPITALIZACAO", "0") == "1"


def _coerce_float(value: Any, default: float = 0.0) -> float:
    if value is None or isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_int(value: Any, default: int = 0) -> int:
    if value is None or isinstance(value, bool):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def parcela_price(pv: float, juros_aa: float, n_meses: int) -> float:
    """Parcela mensal por amortização Price."""
    if n_meses <= 0 or pv <= 0:
        return 0.0
    i = (1 + juros_aa) ** (1 / 12) - 1
    if i <= 0:
        return pv / n_meses
    return pv * i / (1 - (1 + i) ** (-n_meses))


def principal_apos_carencia(pv: float, juros_aa: float, carencia_meses: int = 0) -> float:
    """Principal no fim da carência, com capitalização de juros."""
    if pv <= 0 or carencia_meses <= 0 or juros_aa <= 0 or _CARENCIA_SEM_CAP:
        return max(pv, 0.0)
    i = (1 + juros_aa) ** (1 / 12) - 1
    return pv * (1 + i) ** carencia_meses


def cronograma_price(
    pv: float,
    juros_aa: float,
    prazo_meses: int,
    carencia_meses: int = 0,
) -> dict:
    """Cronograma anual do novo crédito, respeitando carência e ano parcial."""
    pv = max(float(pv or 0), 0.0)
    prazo = int(prazo_meses or 0)
    carencia = int(carencia_meses or 0)
    if pv <= 0 or prazo <= 0:
        return {
            "parcela_mensal": 0.0,
            "principal_amortizado": pv,
            "anos": [],
        }
    if carencia < 0 or carencia >= prazo:
        raise ValueError("A carência deve ser menor que o prazo do crédito.")

    n = prazo - carencia
    principal = principal_apos_carencia(pv, juros_aa, carencia)
    parcela = parcela_price(principal, juros_aa, n)
    anos = []
    for ano in range(1, -(-prazo // 12) + 1):
        inicio = (ano - 1) * 12 + 1
        fim = min(ano * 12, prazo)
        parcelas = sum(1 for mes in range(inicio, fim + 1) if mes > carencia)
        anos.append({
            "ano": ano,
            "parcelas_nova_operacao": parcelas,
            "servico_nova_operacao": round(parcelas * parcela, 2),
        })
    return {
        "parcela_mensal": round(parcela, 2),
        "principal_amortizado": round(principal, 2),
        "anos": anos,
    }


def credito_maximo(
    geracao_caixa_anual: float,
    juros_aa: float,
    prazo_meses: int,
    carencia_meses: int = 0,
    dividas_mensais: float = 0.0,
    dscr_alvo: float = DSCR_APROVAR,
) -> float:
    """Capacidade máxima de endividamento: PV tal que DSCR = dscr_alvo."""
    n = max(prazo_meses - carencia_meses, 0)
    if n <= 0 or juros_aa <= 0 or geracao_caixa_anual <= 0:
        return 0.0
    caixa_disponivel = geracao_caixa_anual / dscr_alvo - 12 * max(dividas_mensais, 0.0)
    if caixa_disponivel <= 0:
        return 0.0
    parcela_max = caixa_disponivel / 12
    i = (1 + juros_aa) ** (1 / 12) - 1
    if i <= 0:
        return round(parcela_max * n, 2)
    pv_no_fim_da_carencia = parcela_max * (1 - (1 + i) ** (-n)) / i
    fator = (
        (1 + i) ** carencia_meses
        if (carencia_meses > 0 and not _CARENCIA_SEM_CAP)
        else 1.0
    )
    return round(pv_no_fim_da_carencia / fator, 2)


def avaliar_capacidade_pagamento(
    geracao_caixa_anual: float,
    credito_valor: float,
    prazo_meses: int,
    juros_aa: float,
    carencia_meses: int = 0,
    dividas_mensais: float = 0.0,
) -> dict:
    """Compatibilidade legada: mantém o contrato histórico do parecer."""
    cronograma = cronograma_price(credito_valor, juros_aa, prazo_meses, carencia_meses)
    _pv = cronograma["principal_amortizado"]
    parcela = cronograma["parcela_mensal"]
    _cap_carencia = (
        {
            "carencia_meses": carencia_meses,
            "principal_liberado": round(credito_valor, 2),
            "principal_amortizado": round(_pv, 2),
            "acrescimo_pct": round((_pv / credito_valor - 1) * 100, 1),
        }
        if _pv > credito_valor > 0
        else None
    )
    servico_anual = 12 * (parcela + max(dividas_mensais, 0.0))
    cap_max = credito_maximo(
        geracao_caixa_anual,
        juros_aa,
        prazo_meses,
        carencia_meses,
        dividas_mensais,
    )

    if servico_anual <= 0:
        return {
            "dscr": None,
            "parcela_mensal": round(parcela, 2),
            "capitalizacao_carencia": _cap_carencia,
            "cronograma_divida": cronograma["anos"],
            "servico_divida_anual": 0.0,
            "geracao_caixa_anual": round(geracao_caixa_anual, 2),
            "capacidade_maxima": cap_max,
            "recomendacao": None,
            "faixa": None,
            "justificativa": "Sem crédito a avaliar.",
        }

    dscr = geracao_caixa_anual / servico_anual
    if geracao_caixa_anual <= 0:
        rec, just = (
            "negar",
            "Operação não gera caixa positivo — sem capacidade de pagamento.",
        )
    elif dscr >= DSCR_APROVAR:
        rec, just = (
            "aprovar",
            f"Cobertura {dscr:.2f} — folga confortável sobre o serviço da dívida.",
        )
    elif dscr >= DSCR_RESSALVA:
        rec, just = (
            "ressalva",
            f"Cobertura {dscr:.2f} — operação cobre a dívida com folga estreita.",
        )
    else:
        rec, just = (
            "negar",
            f"Cobertura {dscr:.2f} — geração de caixa insuficiente para o serviço da dívida.",
        )

    return {
        "dscr": round(dscr, 2),
        "parcela_mensal": round(parcela, 2),
        "servico_divida_anual": round(servico_anual, 2),
        "geracao_caixa_anual": round(geracao_caixa_anual, 2),
        "capacidade_maxima": cap_max,
        "capitalizacao_carencia": _cap_carencia,
        "cronograma_divida": cronograma["anos"],
        "recomendacao": rec,
        "faixa": rec,
        "justificativa": just,
    }


def _fmt_rs(v) -> str:
    return f"R$ {v:,.0f}".replace(",", ".")


def _cashflow_rows(cashflow: dict | None) -> list[dict]:
    cashflow = cashflow or {}
    rows = (
        cashflow.get("projecao_anos")
        or cashflow.get("anos")
        or cashflow.get("years")
        or cashflow.get("rows")
    )
    if rows is None:
        base = _coerce_float(cashflow.get("geracao_caixa_anual"))
        if base > 0:
            rows = [{"ano": 1, "resultado": base}]
        else:
            rows = []
    if not isinstance(rows, list):
        rows = list(rows)
    cleaned = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            row = {}
        cleaned.append(dict(row, ano=_coerce_int(row.get("ano"), index)))
    return cleaned


def _row_result(row: dict) -> float:
    for key in (
        "resultado",
        "geracao_caixa",
        "geracao_caixa_anual",
        "fluxo_livre",
        "cashflow",
    ):
        if key in row:
            value = _coerce_float(row.get(key))
            if key == "fluxo_livre" and value == 0.0:
                continue
            return value
    return 0.0


def _existing_monthly_debt(existing_debt: dict | None) -> float:
    existing_debt = existing_debt or {}
    for key in (
        "parcela_existente_mensal",
        "parcela_total_mensal",
        "dividas_mensais",
        "parcela_mensal",
    ):
        value = _coerce_float(existing_debt.get(key), default=0.0)
        if value > 0:
            return value
    return 0.0


def _build_period_analysis(
    cashflow_rows: list[dict],
    cronograma: dict,
    existing_monthly: float,
) -> list[dict]:
    periods: list[dict] = []
    cronograma_anos = cronograma["anos"] if cronograma["anos"] else []
    for index, row in enumerate(cashflow_rows):
        debt_row = cronograma_anos[index] if index < len(cronograma_anos) else {
            "ano": row["ano"],
            "parcelas_nova_operacao": 0,
            "servico_nova_operacao": 0.0,
        }
        resultado = _row_result(row)
        servico_nova = _coerce_float(debt_row.get("servico_nova_operacao"))
        servico_total = round(servico_nova + 12 * existing_monthly, 2)
        dscr = round(resultado / servico_total, 2) if servico_total > 0 else None
        periods.append(
            {
                "ano": row["ano"],
                "resultado": round(resultado, 2),
                "servico_nova_operacao": round(servico_nova, 2),
                "parcela_nova_mensal": cronograma["parcela_mensal"] if index < len(cronograma_anos) else 0.0,
                "parcela_existente_mensal": round(existing_monthly, 2),
                "servico_divida_anual": servico_total,
                "cobertura": dscr,
                "dscr": dscr,
                "uncovered": dscr is not None and dscr < 1.0,
            }
        )
    return periods


def _best_period(periods: list[dict], *, reverse: bool) -> dict | None:
    numeric = [period for period in periods if period.get("dscr") is not None]
    if not numeric:
        return None
    chosen = max(numeric, key=lambda item: item["dscr"]) if reverse else min(numeric, key=lambda item: item["dscr"])
    return {
        "ano": chosen["ano"],
        "dscr": chosen["dscr"],
        "resultado": chosen["resultado"],
        "servico_divida_anual": chosen["servico_divida_anual"],
        "uncovered": chosen["uncovered"],
    }


def calculate_payment_capacity(
    cashflow: dict,
    debt_request: dict,
    existing_debt: dict | None = None,
) -> dict:
    """Motor puro para capacidade de pagamento.

    A função preserva a leitura da parcela Price, a carência capitalizada e a
    dívda existente, mas acrescenta visão multi-período, DSCR médio/mínimo e o
    período melhor/pior do horizonte informado.
    """
    cashflow = cashflow or {}
    debt_request = debt_request or {}
    existing_debt = existing_debt or {}

    credit_value = _coerce_float(debt_request.get("credito_valor"))
    interest_aa = _coerce_float(debt_request.get("juros_aa"))
    term_months = _coerce_int(debt_request.get("prazo_meses"))
    grace_months = _coerce_int(debt_request.get("carencia_meses"))
    existing_monthly = _existing_monthly_debt(existing_debt)

    cronograma = cronograma_price(credit_value, interest_aa, term_months, grace_months)
    cashflow_rows = _cashflow_rows(cashflow)
    if not cashflow_rows and cashflow.get("geracao_caixa_anual") is not None:
        cashflow_rows = [{"ano": 1, "resultado": _coerce_float(cashflow.get("geracao_caixa_anual"))}]
    if not cashflow_rows:
        cashflow_rows = [{"ano": 1, "resultado": 0.0}]

    periods = _build_period_analysis(cashflow_rows, cronograma, existing_monthly)
    dscrs = [period["dscr"] for period in periods if period.get("dscr") is not None]

    base_cashflow = _coerce_float(cashflow.get("geracao_caixa_anual"))
    if base_cashflow <= 0 and cashflow_rows:
        base_cashflow = _row_result(cashflow_rows[0])

    service_first_year = periods[0]["servico_divida_anual"] if periods else 0.0
    total_service_first_year = service_first_year
    commitment_pct = (
        round(total_service_first_year / base_cashflow * 100, 1)
        if base_cashflow > 0 and total_service_first_year > 0
        else None
    )
    caixa_disponivel = (
        round(base_cashflow / DSCR_APROVAR - 12 * existing_monthly, 2)
        if base_cashflow > 0
        else 0.0
    )
    capacidade_maxima = credito_maximo(
        base_cashflow,
        interest_aa,
        term_months,
        grace_months,
        existing_monthly,
    )

    melhor_periodo = _best_period(periods, reverse=True)
    pior_periodo = _best_period(periods, reverse=False)
    dscr_medio = round(mean(dscrs), 2) if dscrs else None
    dscr_minimo = round(min(dscrs), 2) if dscrs else None
    uncovered_periods = [period["ano"] for period in periods if period.get("uncovered")]

    summary = {
        "geracao_caixa_anual": round(base_cashflow, 2),
        "servico_divida_anual": round(service_first_year, 2),
        "servico_divida_media_anual": round(
            mean(period["servico_divida_anual"] for period in periods), 2
        )
        if periods
        else 0.0,
        "caixa_disponivel": caixa_disponivel,
        "comprometimento_pct": commitment_pct,
        "capacidade_maxima_estimativa": capacidade_maxima,
        "dscr_medio": dscr_medio,
        "dscr_minimo": dscr_minimo,
        "cobertura_media": dscr_medio,
        "cobertura_minima": dscr_minimo,
        "melhor_periodo": melhor_periodo,
        "pior_periodo": pior_periodo,
        "uncovered_periods": uncovered_periods,
    }

    legacy = avaliar_capacidade_pagamento(
        base_cashflow,
        credit_value,
        term_months,
        interest_aa,
        grace_months,
        existing_monthly,
    )

    analysis = {
        "cashflow": deepcopy(cashflow) if isinstance(cashflow, dict) else {},
        "debt_request": deepcopy(debt_request) if isinstance(debt_request, dict) else {},
        "existing_debt": deepcopy(existing_debt) if isinstance(existing_debt, dict) else {},
        "cronograma_divida": cronograma["anos"],
        "periods": periods,
        **summary,
    }
    if dscr_minimo is not None:
        analysis["uncovered"] = dscr_minimo < 1.0
    else:
        analysis["uncovered"] = False

    return {
        "analysis": analysis,
        "periods": periods,
        "legacy": legacy,
    }


def avaliar_capacidade_no_prazo(conclusao_ano1: dict, projecao_anos: list, prazo_meses: int) -> dict:
    """Reavalia a capacidade de pagamento sobre TODOS os anos do financiamento."""
    base = dict(conclusao_ano1)
    if not projecao_anos:
        return base
    if not base.get("cronograma_divida") and not base.get("parcela_mensal"):
        return base

    n_anos = max(1, min(-(-prazo_meses // 12), len(projecao_anos)))
    avaliados = projecao_anos[:n_anos]
    dscrs = [(a["ano"], a["dscr"]) for a in avaliados if a.get("dscr") is not None]
    if not dscrs:
        return base

    ano_pior, dscr_min = min(dscrs, key=lambda t: t[1])
    dscr_medio = sum(d for _, d in dscrs) / len(dscrs)
    n_viaveis = sum(1 for a in avaliados if a.get("viavel"))

    memoria = [
        {
            "passo": "Prazo do crédito",
            "valor": f"{prazo_meses} meses",
            "detalhe": f"A capacidade de pagamento é avaliada sobre {n_anos} ano(s) de projeção, não apenas o primeiro.",
        },
        {
            "passo": "Serviço da dívida",
            "valor": "cronograma anual",
            "detalhe": "O DSCR usa os vencimentos efetivos de cada ano; não multiplica automaticamente a parcela por doze.",
        },
    ]
    for item in base.get("cronograma_divida") or []:
        memoria.append(
            {
                "passo": f"Serviço da nova operação — ano {item['ano']}",
                "valor": _fmt_rs(item["servico_nova_operacao"]),
                "detalhe": (
                    f"{item['parcelas_nova_operacao']} parcela(s) de {_fmt_rs(base['parcela_mensal'])}; carência e ano parcial respeitados."
                ),
            }
        )
    _cap = base.get("capitalizacao_carencia")
    if _cap:
        memoria.append(
            {
                "passo": "Carência capitaliza juros",
                "valor": f"{_fmt_rs(_cap['principal_liberado'])} → {_fmt_rs(_cap['principal_amortizado'])}",
                "detalhe": (
                    f"Durante os {_cap['carencia_meses']} meses de carência o saldo rende juros e é incorporado ao principal (+{_cap['acrescimo_pct']:.1f}%). "
                    f"A amortização recai sobre o saldo maior, então a parcela sobe na mesma proporção."
                ),
            }
        )
    for ano, d in dscrs:
        res = next((a.get("resultado") for a in avaliados if a["ano"] == ano), None)
        nota = "liquida o estoque de animais prontos declarado na ficha" if ano == 1 else "vende apenas a produção corrente do rebanho"
        memoria.append(
            {
                "passo": f"DSCR do ano {ano}",
                "valor": f"{d:.2f}",
                "detalhe": f"Geração de caixa de {_fmt_rs(res)} — {nota}." if res is not None else nota,
            }
        )

    if dscr_min >= DSCR_APROVAR:
        rec = "aprovar"
        just = (
            f"Cobertura mínima {dscr_min:.2f} no ano {ano_pior} — a operação sustenta o serviço da dívida em todos os {n_anos} anos do prazo."
        )
    elif dscr_min >= DSCR_RESSALVA:
        rec = "ressalva"
        just = (
            f"Cobertura cai para {dscr_min:.2f} no ano {ano_pior}. A operação ainda cobre a dívida, mas sem folga em todo o prazo."
        )
    else:
        rec = "negar"
        just = (
            f"Cobertura cai para {dscr_min:.2f} no ano {ano_pior}, abaixo de 1,00 — a operação deixa de cobrir a dívida antes do fim do prazo."
        )

    recomendacao_ano1 = base.get("recomendacao")
    rebaixado = recomendacao_ano1 is not None and rec != recomendacao_ano1
    memoria.append(
        {
            "passo": "Ano crítico",
            "valor": f"ano {ano_pior} · DSCR {dscr_min:.2f}",
            "detalhe": "É o ano mais fraco do prazo, e é ele que define a recomendação — a dívida vence independentemente.",
        }
    )
    memoria.append(
        {
            "passo": "Anos viáveis",
            "valor": f"{n_viaveis} de {n_anos}",
            "detalhe": "Ano viável = gera caixa positivo e cobre o serviço da dívida.",
        }
    )
    if rebaixado:
        memoria.append(
            {
                "passo": "Rebaixamento",
                "valor": f"{recomendacao_ano1.upper()} → {rec.upper()}",
                "detalhe": f"O ano 1 isolado indicava {recomendacao_ano1} (DSCR {base['dscr']:.2f}), mas ele liquida o estoque acumulado e não se repete.",
            }
        )

    base.update(
        {
            "recomendacao": rec,
            "faixa": rec,
            "justificativa": just,
            "dscr_ano1": next((d for ano, d in dscrs if ano == 1), None),
            "dscr_minimo": round(dscr_min, 2),
            "dscr_medio": round(dscr_medio, 2),
            "ano_critico": ano_pior,
            "anos_avaliados": n_anos,
            "anos_viaveis": n_viaveis,
            "rebaixado_no_prazo": rebaixado,
            "memoria": memoria,
        }
    )
    return base


def _catalogo_proveniencia():
    from services.garantia import DESAGIO_PADRAO, LTV_APROVAR, LTV_RESSALVA
    from services.endividamento import COMPROMETIMENTO_ALERTA
    import services.parametros_zootecnicos as _pz
    import services.nivel_tecnologico as _nt

    return catalogo(
        DSCR_APROVAR,
        DSCR_RESSALVA,
        LTV_APROVAR,
        LTV_RESSALVA,
        DESAGIO_PADRAO,
        COMPROMETIMENTO_ALERTA,
        do_modulo(_pz, _nt),
    )


def resumo_proveniencia() -> dict:
    cat = _catalogo_proveniencia()
    return {"parametros": cat, "resumo": _resumo_prov(cat)}
