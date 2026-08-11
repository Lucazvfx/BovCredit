import pytest

from services.fluxo_mensal_credito import projetar_fluxo_mensal
from services.parecer_credito import parcela_price, principal_apos_carencia
from services.cashflow_engine import project_cashflow


def test_legacy_linear_fallback_preserves_shape_and_marks_estimated():
    anos = [
        {"ano": 1, "receita": 12_000.0, "custo": 24_000.0, "servico_divida_anual": 12_000.0},
        {"ano": 2, "receita": 24_000.0, "custo": 12_000.0, "servico_divida_anual": 0.0},
    ]

    result = projetar_fluxo_mensal(anos)

    assert result["metodo"] == "distribuicao_linear_anual_estimada"
    assert result["saldo_minimo"] == pytest.approx(-24_000.0, abs=0.01)
    assert result["mes_critico"] == {"ano": 1, "mes": 12}
    assert len(result["meses"]) == 24
    assert "estimad" in result["aviso"].lower()

    first = result["meses"][0]
    assert first["ano"] == 1
    assert first["mes"] == 1
    assert first["estimated"] is True
    assert first["receita_estimada"] == pytest.approx(1_000.0, abs=0.01)
    assert first["custo_operacional_estimado"] == pytest.approx(2_000.0, abs=0.01)
    assert first["servico_divida"] == pytest.approx(1_000.0, abs=0.01)
    assert first["saldo_acumulado"] == pytest.approx(-2_000.0, abs=0.01)


def test_project_cashflow_applies_custom_calendar_by_category():
    annual_projection = {
        "years": [
            {
                "calf_sales": 120.0,
                "finished_sales": 240.0,
                "purchases": 60.0,
                "costs": 120.0,
                "investments": 0.0,
            }
        ]
    }
    calendar = {
        "calf_sales": [0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        "finished_sales": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0],
        "purchases": [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        "costs": [1] * 12,
    }

    result = project_cashflow(
        annual_projection,
        {"servico_divida_anual": 0.0},
        horizon_months=12,
        calendar=calendar,
    )

    rows = result["months"]
    assert len(rows) == 12
    assert result["estimated"] is False
    assert result["warnings"] == []
    assert rows[0]["estimated"] is False
    assert rows[2]["entradas"] == pytest.approx(120.0, abs=0.01)
    assert rows[10]["entradas"] == pytest.approx(240.0, abs=0.01)
    assert rows[0]["investimentos"] == pytest.approx(60.0, abs=0.01)
    assert sum(row["entradas"] for row in rows) == pytest.approx(360.0, abs=0.01)
    assert sum(row["custos_operacionais"] for row in rows) == pytest.approx(120.0, abs=0.01)
    assert sum(row["investimentos"] for row in rows) == pytest.approx(60.0, abs=0.01)


def test_project_cashflow_keeps_valid_calendar_when_seasonality_overlay_is_invalid():
    annual_projection = {
        "years": [
            {
                "calf_sales": 120.0,
                "finished_sales": 0.0,
                "purchases": 0.0,
                "costs": 0.0,
                "investments": 0.0,
            }
        ]
    }
    calendar = {
        "calf_sales": [0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    }
    seasonality = {
        "calf_sales": [0] * 12,
    }

    result = project_cashflow(
        annual_projection,
        {"servico_divida_anual": 0.0},
        horizon_months=12,
        calendar=calendar,
        seasonality=seasonality,
    )

    rows = result["months"]
    assert rows[2]["entradas"] == pytest.approx(120.0, abs=0.01)
    assert rows[0]["entradas"] == pytest.approx(0.0, abs=0.01)
    assert sum(row["entradas"] for row in rows) == pytest.approx(120.0, abs=0.01)
    assert any("seasonality" in warning.lower() for warning in result["warnings"])


def test_project_cashflow_preserves_source_ano_labels_when_present():
    annual_projection = {
        "years": [
            {"ano": 2024, "receita": 120.0, "custo": 24.0, "servico_divida_anual": 12.0},
            {"ano": 2027, "receita": 120.0, "custo": 24.0, "servico_divida_anual": 12.0},
        ]
    }

    result = project_cashflow(annual_projection, {}, horizon_months=24)
    rows = result["months"]

    assert rows[0]["ano"] == 2024
    assert rows[11]["ano"] == 2024
    assert rows[12]["ano"] == 2027
    assert rows[-1]["ano"] == 2027


def test_project_cashflow_marks_zero_sum_seasonality_as_estimated():
    annual_projection = {
        "years": [
            {"receita": 120.0, "custo": 0.0, "servico_divida_anual": 0.0},
        ]
    }

    result = project_cashflow(
        annual_projection,
        {"servico_divida_anual": 0.0},
        horizon_months=12,
        seasonality={
            "entradas": [0] * 12,
            "custos_operacionais": [1] * 12,
            "investimentos": [1] * 12,
        },
    )

    rows = result["months"]
    assert result["estimated"] is True
    assert rows[0]["estimated"] is True
    assert any("seasonality" in warning.lower() for warning in result["warnings"])


@pytest.mark.parametrize("horizon_months", [12, 24, 36, 48, 60])
def test_project_cashflow_rolls_forward_for_supported_horizons(horizon_months):
    annual_projection = {
        "years": [
            {"receita": 120.0, "custo": 24.0, "servico_divida_anual": 12.0},
        ]
    }

    result = project_cashflow(
        annual_projection,
        {"servico_divida_anual": 12.0},
        horizon_months=horizon_months,
    )

    rows = result["months"]
    assert len(rows) == horizon_months
    assert rows[0]["saldo_inicial"] == pytest.approx(0.0, abs=0.01)
    assert rows[0]["saldo_final"] == pytest.approx(7.0, abs=0.01)
    assert rows[-1]["saldo_final"] == pytest.approx(7.0 * horizon_months, abs=0.01)


def test_project_cashflow_preserves_grace_period_with_price_schedule():
    annual_projection = {
        "years": [
            {"receita": 120.0, "custo": 0.0, "servico_divida_anual": 0.0},
        ]
    }
    debt_schedule = {
        "credito_valor": 120_000.0,
        "juros_aa": 0.12,
        "prazo_meses": 12,
        "carencia_meses": 3,
    }

    result = project_cashflow(annual_projection, debt_schedule, horizon_months=12)
    rows = result["months"]
    principal = principal_apos_carencia(120_000.0, 0.12, 3)
    parcela = parcela_price(principal, 0.12, 9)

    assert rows[0]["parcelas"] == pytest.approx(0.0, abs=0.01)
    assert rows[1]["parcelas"] == pytest.approx(0.0, abs=0.01)
    assert rows[2]["parcelas"] == pytest.approx(0.0, abs=0.01)
    assert rows[3]["parcelas"] + rows[3]["juros"] == pytest.approx(parcela, abs=0.01)
    assert rows[3]["parcelas"] > 0.0
    assert rows[3]["juros"] > 0.0
