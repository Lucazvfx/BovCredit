from copy import deepcopy

from services.stress_engine import default_stress_scenarios, run_stress_tests


def _base_analysis():
    return {
        "projecao_anos": [
            {"ano": 1, "receita": 300_000.0, "custo": 120_000.0, "resultado": 180_000.0, "dscr": 1.55},
            {"ano": 2, "receita": 260_000.0, "custo": 150_000.0, "resultado": 110_000.0, "dscr": 1.02},
            {"ano": 3, "receita": 240_000.0, "custo": 160_000.0, "resultado": 80_000.0, "dscr": 0.92},
        ],
        "conclusao": {
            "dscr_minimo": 0.92,
            "ano_critico": 3,
            "recomendacao": "negar",
        },
        "servico_divida_anual": 87_000.0,
        "geracao_caixa_anual": 180_000.0,
    }


def test_default_stress_scenarios_cover_the_expected_shocks():
    labels = {scenario["nome"] for scenario in default_stress_scenarios()}
    assert {
        "queda_preco",
        "custo_alto",
        "natalidade_baixa",
        "mortalidade_alta",
        "gmd_baixo",
        "comercializacao_atrasada",
        "choque_combinado",
    }.issubset(labels)


def test_run_stress_tests_preserves_base_analysis_and_lists_applied_changes():
    base = _base_analysis()
    original = deepcopy(base)
    scenarios = [
        {
            "nome": "moderado",
            "price_pct": -10,
            "cost_pct": 8,
            "natality_pct": -5,
            "mortality_pct": 3,
            "gmd_pct": -8,
            "commercialization_delay_months": 2,
        },
        {
            "nome": "severo",
            "price_pct": -20,
            "cost_pct": 15,
            "natality_pct": -10,
            "mortality_pct": 8,
            "gmd_pct": -15,
            "commercialization_delay_months": 4,
        },
    ]

    result = run_stress_tests(base, scenarios)

    assert base == original, "o motor de stress não pode mutar a análise base"
    assert result["base_analysis"] == original

    severe = next(item for item in result["scenarios"] if item["nome"] == "severo")
    assert severe["uncovered"] is True
    assert severe["dscr_minimo"] < 1.0
    assert severe["applied_changes"] == [
        "price_pct -20%",
        "cost_pct +15%",
        "natality_pct -10%",
        "mortality_pct +8%",
        "gmd_pct -15%",
        "commercialization_delay_months +4m",
    ]
    assert severe["base_analysis"] == original
    assert severe["analysis"]["base_analysis"] == original
