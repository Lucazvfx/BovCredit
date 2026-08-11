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


def test_run_stress_tests_keeps_each_period_own_debt_service():
    base = {
        "projecao_anos": [
            {
                "ano": 1,
                "receita": 300_000.0,
                "custo": 120_000.0,
                "resultado": 180_000.0,
                "servico_divida_anual": 60_000.0,
                "dscr": 3.0,
            },
            {
                "ano": 2,
                "receita": 260_000.0,
                "custo": 150_000.0,
                "resultado": 110_000.0,
                "servico_divida_anual": 90_000.0,
                "dscr": 1.22,
            },
            {
                "ano": 3,
                "receita": 240_000.0,
                "custo": 160_000.0,
                "resultado": 80_000.0,
                "servico_divida_anual": 30_000.0,
                "dscr": 2.67,
            },
        ],
        "conclusao": {
            "dscr_minimo": 1.22,
            "ano_critico": 2,
            "recomendacao": "ressalva",
        },
        "servico_divida_anual": 60_000.0,
        "geracao_caixa_anual": 180_000.0,
    }

    result = run_stress_tests(base, [{"nome": "neutro"}])
    scenario = result["scenarios"][0]
    periods = scenario["analysis"]["projecao_anos"]

    assert [period["servico_divida_anual"] for period in periods] == [
        60_000.0,
        90_000.0,
        30_000.0,
    ]
    assert [period["dscr"] for period in periods] == [3.0, 1.22, 2.67]
    assert scenario["analysis"]["pior_periodo"]["ano"] == 2
    assert scenario["analysis"]["conclusao"]["ano_critico"] == 2
