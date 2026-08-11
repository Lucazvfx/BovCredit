import pytest

from services.fluxo_caixa_gep import calcular_fluxo_gep
from services.parametros_zootecnicos import PESO_BEZERRA_ARR, PESO_BOI_ARR, PESO_VACA_ARR
from services.economic_engine import (
    calculate_costs,
    calculate_economic_result,
    calculate_revenues,
)


def test_calculate_revenues_breaks_out_categories_and_per_unit_metrics():
    production = {
        "bois_vendidos": 3,
        "matrizes_descartadas": 2,
        "bezerras_vendidas": 4,
        "machos_vendidos": 5,
        "cabecas_vendidas": 14,
        "arrobas_vendidas": (3 * 20.53) + (2 * 15.33) + (4 * 6.00) + (5 * 6.67),
    }
    prices = {
        "preco_boi_arr": 347.50,
        "preco_vaca_arr": 321.00,
        "preco_bezerra_cab": 3_031.21,
        "preco_bezerro_cab": 3_368.01,
    }

    result = calculate_revenues(production, prices)
    esperado_bois = 3 * PESO_BOI_ARR * 347.50
    esperado_vacas = 2 * PESO_VACA_ARR * 321.00
    esperado_bezerras = 4 * 3_031.21
    esperado_machos = 5 * 3_368.01

    assert result["valid"] is True
    assert result["warnings"] == []
    assert result["receita_por_categoria"]["bois_vendidos"] == pytest.approx(
        round(esperado_bois, 2), abs=0.01
    )
    assert result["receita_por_categoria"]["matrizes_descartadas"] == pytest.approx(
        round(esperado_vacas, 2), abs=0.01
    )
    assert result["receita_por_categoria"]["bezerras_vendidas"] == pytest.approx(
        round(esperado_bezerras, 2), abs=0.01
    )
    assert result["receita_por_categoria"]["machos_vendidos"] == pytest.approx(
        round(esperado_machos, 2), abs=0.01
    )
    assert result["receita_total"] == pytest.approx(
        esperado_bois + esperado_vacas + esperado_bezerras + esperado_machos,
        abs=0.01,
    )
    assert result["receita_por_cabeca"] == pytest.approx(
        result["receita_total"] / 14, abs=0.01
    )
    assert result["receita_por_arroba"] == pytest.approx(
        result["receita_total"] / production["arrobas_vendidas"], abs=0.01
    )


def test_calculate_revenues_reports_missing_prices_instead_of_filling_them():
    production = {
        "bois_vendidos": 1,
        "matrizes_descartadas": 1,
        "bezerras_vendidas": 1,
        "machos_vendidos": 1,
    }

    result = calculate_revenues(production, {"preco_boi_arr": 347.50})

    assert result["valid"] is False
    assert result["receita_total"] is None
    assert any("preco_vaca_arr" in warning for warning in result["warnings"])
    assert any("preco_bezerra_cab" in warning for warning in result["warnings"])
    assert any("preco_bezerro_cab" in warning for warning in result["warnings"])


def test_calculate_costs_keeps_maintenance_plus_replacement_as_operational_cost():
    production = {
        "cabecas": 800,
        "arrobas_vendidas": 137.0,
    }
    cost_parameters = {
        "custo_fixo_operacional": 120_000.0,
        "custo_variavel_operacional": 279_000.0,
        "custo_reposicao": 972_203.71,
        "custo_investimento": 12_500.0,
        "reposicao_reprodutores": 7_419.54,
    }

    result = calculate_costs(production, cost_parameters)

    assert result["valid"] is True
    assert result["warnings"] == []
    assert result["custo_manutencao"] == pytest.approx(399_000.0, abs=0.01)
    assert result["custo_operacional"] == pytest.approx(
        result["custo_manutencao"] + result["custo_reposicao"], abs=0.01
    )
    assert result["custo_investimento"] == pytest.approx(12_500.0, abs=0.01)
    assert result["reposicao_reprodutores"] == pytest.approx(7_419.54, abs=0.01)


def test_calculate_costs_flags_partial_operating_input_without_losing_numbers():
    production = {
        "cabecas": 800,
        "arrobas_vendidas": 137.0,
    }
    cost_parameters = {
        "custo_fixo_operacional": 120_000.0,
        "custo_reposicao": 972_203.71,
    }

    result = calculate_costs(production, cost_parameters)

    assert result["valid"] is True
    assert result["partial_input"] is True
    assert any("fixed" in warning or "variable" in warning for warning in result["warnings"])
    assert result["custo_manutencao"] == pytest.approx(120_000.0, abs=0.01)
    assert result["custo_operacional"] == pytest.approx(
        result["custo_manutencao"] + result["custo_reposicao"], abs=0.01
    )


def test_calculate_economic_result_matches_current_fluxo_gep_contract():
    revenues = {"receita_total": 1_354_167.79}
    costs = {
        "custo_manutencao": 399_000.0,
        "custo_reposicao": 972_203.71,
        "custo_operacional": 1_371_203.71,
        "reposicao_reprodutores": 7_419.54,
        "custo_investimento": 0.0,
        "cabecas": 800,
        "arrobas_vendidas": 137.0,
    }

    legacy = calcular_fluxo_gep(
        receita_caixa=revenues["receita_total"],
        custo_caixa=costs["custo_operacional"],
        valor_rebanho_ini=2_303_212.30,
        valor_rebanho_fim=2_379_320.98,
        reposicao_reprodutores=costs["reposicao_reprodutores"],
    )
    result = calculate_economic_result(revenues, costs, inventory_change=76_108.68)

    assert result["receita_total"] == pytest.approx(revenues["receita_total"], abs=0.01)
    assert result["custo_operacional"] == pytest.approx(costs["custo_operacional"], abs=0.01)
    assert result["resultado_operacional"] == pytest.approx(
        legacy["resultado_operacional"], abs=0.01
    )
    assert result["resultado_economico"] == pytest.approx(
        legacy["resultado_economico"], abs=0.01
    )
    assert result["margem_bruta"] == pytest.approx(
        revenues["receita_total"] - costs["custo_operacional"], abs=0.01
    )
    assert result["preco_breakeven"] == pytest.approx(
        costs["custo_operacional"] / costs["arrobas_vendidas"], abs=0.01
    )
    assert result["preco_breakeven_unidade"] == "R$/arroba"
    assert result["custo_por_cabeca"] == pytest.approx(
        costs["custo_operacional"] / costs["cabecas"], abs=0.01
    )
    assert result["receita_por_cabeca"] == pytest.approx(
        revenues["receita_total"] / costs["cabecas"], abs=0.01
    )


def test_calculate_economic_result_reconstructs_missing_operational_cost_from_components():
    revenues = {"receita_total": 1_354_167.79}
    costs = {
        "custo_manutencao": 399_000.0,
        "custo_reposicao": 972_203.71,
        "reposicao_reprodutores": 7_419.54,
        "custo_investimento": 0.0,
        "cabecas": 800,
        "arrobas_vendidas": 137.0,
    }

    result = calculate_economic_result(revenues, costs, inventory_change=76_108.68)

    assert result["valid"] is True
    assert result["warnings"] == []
    assert result["custo_operacional"] == pytest.approx(
        costs["custo_manutencao"] + costs["custo_reposicao"], abs=0.01
    )
    assert result["margem_bruta"] == pytest.approx(
        revenues["receita_total"] - result["custo_operacional"], abs=0.01
    )
    assert result["resultado_antes_reposicao"] == pytest.approx(
        revenues["receita_total"] - costs["custo_manutencao"], abs=0.01
    )
