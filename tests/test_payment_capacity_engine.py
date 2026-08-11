from copy import deepcopy

import pytest

from services.endividamento import consolidar
from services.parecer_credito import (
    avaliar_capacidade_pagamento,
    credito_maximo,
    cronograma_price,
)
from services.payment_capacity_engine import calculate_payment_capacity


def _cashflow_base():
    return {
        "geracao_caixa_anual": 180_000.0,
        "projecao_anos": [
            {"ano": 1, "resultado": 180_000.0},
            {"ano": 2, "resultado": 140_000.0},
            {"ano": 3, "resultado": 95_000.0},
        ],
    }


def _debt_request():
    return {
        "credito_valor": 500_000.0,
        "prazo_meses": 36,
        "juros_aa": 0.125,
        "carencia_meses": 6,
    }


def test_calculate_payment_capacity_preserves_legacy_price_grace_and_existing_debt():
    cashflow = _cashflow_base()
    debt_request = _debt_request()
    existing_debt = consolidar(
        dividas_mensais_legado=1_500.0,
        geracao_caixa_anual=cashflow["geracao_caixa_anual"],
    )

    legacy = avaliar_capacidade_pagamento(
        cashflow["geracao_caixa_anual"],
        debt_request["credito_valor"],
        debt_request["prazo_meses"],
        debt_request["juros_aa"],
        debt_request["carencia_meses"],
        existing_debt["parcela_existente_mensal"],
    )

    result = calculate_payment_capacity(
        deepcopy(cashflow),
        deepcopy(debt_request),
        deepcopy(existing_debt),
    )

    assert result["legacy"]["parcela_mensal"] == pytest.approx(
        legacy["parcela_mensal"], abs=0.01
    )
    assert result["legacy"]["servico_divida_anual"] == pytest.approx(
        legacy["servico_divida_anual"], abs=0.01
    )
    assert result["analysis"]["capacidade_maxima_estimativa"] == pytest.approx(
        credito_maximo(
            cashflow["geracao_caixa_anual"],
            debt_request["juros_aa"],
            debt_request["prazo_meses"],
            debt_request["carencia_meses"],
            existing_debt["parcela_existente_mensal"],
        ),
        abs=0.01,
    )

    cronograma = cronograma_price(
        debt_request["credito_valor"],
        debt_request["juros_aa"],
        debt_request["prazo_meses"],
        debt_request["carencia_meses"],
    )
    periods = result["periods"]
    assert len(periods) == len(cashflow["projecao_anos"])

    expected_dscrs = []
    for period, year_row, debt_row in zip(
        periods, cashflow["projecao_anos"], cronograma["anos"]
    ):
        expected_service = debt_row["servico_nova_operacao"] + 12 * existing_debt[
            "parcela_existente_mensal"
        ]
        expected_dscr = round(year_row["resultado"] / expected_service, 2)
        expected_dscrs.append(expected_dscr)
        assert period["servico_divida_anual"] == pytest.approx(
            expected_service, abs=0.01
        )
        assert period["dscr"] == pytest.approx(expected_dscr, abs=0.01)
        assert period["uncovered"] is (expected_dscr < 1.0)

    assert result["analysis"]["dscr_medio"] == pytest.approx(
        sum(expected_dscrs) / len(expected_dscrs), abs=0.01
    )
    assert result["analysis"]["dscr_minimo"] == pytest.approx(
        min(expected_dscrs), abs=0.01
    )
    assert result["analysis"]["melhor_periodo"]["ano"] == 1
    assert result["analysis"]["pior_periodo"]["ano"] == 3


def test_calculate_payment_capacity_marks_uncovered_periods_and_keeps_estimate():
    cashflow = {
        "geracao_caixa_anual": 120_000.0,
        "projecao_anos": [
            {"ano": 1, "resultado": 120_000.0},
            {"ano": 2, "resultado": 45_000.0},
        ],
    }
    debt_request = {
        "credito_valor": 100_000.0,
        "prazo_meses": 24,
        "juros_aa": 0.10,
        "carencia_meses": 0,
    }

    result = calculate_payment_capacity(cashflow, debt_request)

    assert result["analysis"]["uncovered_periods"] == [2]
    assert result["periods"][1]["uncovered"] is True
    assert result["analysis"]["caixa_disponivel"] > 0
    assert result["analysis"]["capacidade_maxima_estimativa"] > 0
    assert result["legacy"]["recomendacao"] in {"aprovar", "ressalva", "negar"}


def test_calculate_payment_capacity_zeros_debt_service_after_loan_term():
    cashflow = {
        "geracao_caixa_anual": 180_000.0,
        "projecao_anos": [
            {"ano": 1, "resultado": 180_000.0},
            {"ano": 2, "resultado": 140_000.0},
            {"ano": 3, "resultado": 95_000.0},
            {"ano": 4, "resultado": 90_000.0},
            {"ano": 5, "resultado": 85_000.0},
        ],
    }
    debt_request = {
        "credito_valor": 500_000.0,
        "prazo_meses": 30,
        "juros_aa": 0.125,
        "carencia_meses": 6,
    }

    result = calculate_payment_capacity(cashflow, debt_request)
    periods = result["periods"]
    cronograma = result["analysis"]["cronograma_divida"]

    assert [row["servico_nova_operacao"] for row in periods[:3]] == [
        pytest.approx(cronograma[0]["servico_nova_operacao"], abs=0.01),
        pytest.approx(cronograma[1]["servico_nova_operacao"], abs=0.01),
        pytest.approx(cronograma[2]["servico_nova_operacao"], abs=0.01),
    ]
    for period in periods[3:]:
        assert period["servico_nova_operacao"] == 0.0
        assert period["servico_divida_anual"] == 0.0
        assert period["dscr"] is None
        assert period["uncovered"] is False
