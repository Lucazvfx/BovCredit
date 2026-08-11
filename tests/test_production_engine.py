from __future__ import annotations

import pytest

import ml_engine
from ml_engine import CENARIOS, PARAMS_POR_CICLO, simular_cenario
from services.engine.contracts import HerdState
from services.engine.parameter_registry import resolve_parameters
from services.production_engine import (
    project_cria,
    project_engorda,
    project_full_cycle,
    project_production,
    project_recria,
)


CRIA = [300, 280, 200, 80, 100, 40, 150, 10, 600, 15]
RECRIA = [0, 0, 150, 15, 374, 0, 209, 0, 5, 0]
ENGORDA = [10, 8, 20, 18, 50, 80, 20, 120, 10, 400]
CICLO_COMPLETO = [80, 80, 50, 50, 60, 60, 90, 40, 220, 60]


def _state(values: list[float]) -> HerdState:
    return HerdState(values=values, source="MANUAL", farm_id=1, metadata={})


def _scenario_mods(scenario: str = "conservador") -> dict[str, float]:
    return CENARIOS[scenario]["mods"]


def _scaled_price(value: float, scenario: str = "conservador") -> float:
    return float(value) * _scenario_mods(scenario)["preco"]


def _cria_parameters(
    *,
    scenario: str = "conservador",
    venda_bez_pct: float = PARAMS_POR_CICLO["CRIA"]["venda_bez_pct"],
    desc_mat_pct: float = PARAMS_POR_CICLO["CRIA"]["desc_mat_pct"],
) -> dict:
    registry = resolve_parameters({}, "CRIA")
    mods = _scenario_mods(scenario)
    return {
        "nat_pct": float(registry["natalidade_pct"]) * mods["nat"],
        "mort_pct": float(registry["mortalidade_pct"]) * mods["mort"],
        "desmama_pct": None,
        "venda_bez_pct": float(venda_bez_pct),
        "preco_arroba_bezerro": _scaled_price(330.0, scenario),
        "custo_arroba": 11.31,
        "peso_matriz": 15.33,
        "peso_bezerra": 6.0,
        "preco_vaca_arr": None,
        "desc_mat_pct": float(desc_mat_pct),
    }


def _recria_parameters(
    *,
    scenario: str = "conservador",
    preco_bezerro_cab: float | None = None,
) -> dict:
    registry = resolve_parameters({}, "RECRIA")
    mods = _scenario_mods(scenario)
    params = {
        "mort_pct": float(resolve_parameters({}, "CRIA")["mortalidade_pct"]) * mods["mort"],
        "preco_arroba": _scaled_price(320.0, scenario),
        "peso_entrada_arr": 6.5,
        "peso_saida_arr": 13.5,
        "meses_recria": 12,
        "custo_arroba": 119.0,
        "preco_reposicao_cab": None if preco_bezerro_cab is None else float(preco_bezerro_cab) * mods["preco"],
    }
    # Registry-backed defaults are included for the new engine even if the
    # legacy projection does not consume all of them directly.
    params.update(
        {
            "ganho_arroba_mes": float(registry["ganho_arroba_mes"]),
            "peso_garrote_arr": float(registry["peso_garrote_arr"]),
            "peso_bezerra_arr": float(registry["peso_bezerra_arr"]),
        }
    )
    return params


def _engorda_parameters(*, scenario: str = "conservador", ganho_peso_kg_dia: float = 0.85) -> dict:
    registry = resolve_parameters({}, "ENGORDA")
    mods = _scenario_mods(scenario)
    return {
        "mort_pct": float(resolve_parameters({}, "CRIA")["mortalidade_pct"]) * mods["mort"],
        "preco_arroba": _scaled_price(330.0, scenario),
        "peso_entrada_kg": 405.0,
        "peso_saida_kg": 520.0,
        "rendimento_carcaca": float(registry["rendimento_carcaca_pct"]),
        "custo_arroba": 17.21,
        "dias_engorda": None,
        "ganho_peso_kg_dia": float(ganho_peso_kg_dia),
        "nat_mod": mods["nat"],
    }


def _full_cycle_parameters(*, scenario: str = "conservador") -> dict:
    registry = resolve_parameters({}, "CICLO_COMPLETO")
    mods = _scenario_mods(scenario)
    return {
        "nat_pct": float(registry["natalidade_pct"]) * mods["nat"],
        "mort_pct": float(registry["mortalidade_pct"]) * mods["mort"],
        "desc_mat_pct": PARAMS_POR_CICLO["CICLO_COMPLETO"]["desc_mat_pct"] * mods["desc"],
        "prop_boi": PARAMS_POR_CICLO["CICLO_COMPLETO"]["prop_boi"],
        "renov_boi_pct": PARAMS_POR_CICLO["CICLO_COMPLETO"]["renov_boi_pct"],
        "venda_bez_pct": PARAMS_POR_CICLO["CICLO_COMPLETO"]["venda_bez_pct"],
        "preco_arroba": _scaled_price(320.0, scenario),
        "custo_arroba": 122.0,
        "peso_boi": float(registry["peso_boi_arr"]),
        "peso_vaca": float(registry["peso_vaca_arr"]),
        "peso_bezerra": float(resolve_parameters({}, "RECRIA")["peso_bezerra_arr"]),
        "peso_garrote": float(resolve_parameters({}, "RECRIA")["peso_garrote_arr"]),
        "preco_boi_arr": None,
        "preco_vaca_arr": None,
        "preco_bezerra_cab": None,
        "preco_bezerro_cab": None,
    }


def _legacy_year1(values: list[float], ciclo: str, **kwargs) -> dict:
    return simular_cenario(values, cenario="conservador", ciclo=ciclo, anos=1, **kwargs)["anos"][0]


def _legacy_years(values: list[float], ciclo: str, years: int, **kwargs) -> list[dict]:
    return simular_cenario(values, cenario="conservador", ciclo=ciclo, anos=years, **kwargs)["anos"]


def _compare_years(new: dict, legacy: dict, *, keys: tuple[str, ...]) -> None:
    tolerances = {
        "bezerros": 1.0,
        "receita": 25.0,
        "custo": 25.0,
        "custo_manutencao": 25.0,
        "custo_compra_desmama": 1.0,
        "custo_reposicao": 25.0,
        "resultado": 25.0,
    }
    for key in keys:
        assert new[key] == pytest.approx(legacy[key], abs=tolerances.get(key, 0.01)), key


def test_project_cria_matches_legacy_characterization():
    state = _state(CRIA)
    params = _cria_parameters()
    legacy = _legacy_year1(
        CRIA,
        "CRIA",
        preco_arroba=330.0,
        custo_arroba=11.31,
        venda_bez_pct=PARAMS_POR_CICLO["CRIA"]["venda_bez_pct"],
    )

    projected = project_cria(state, params, years=1)

    assert projected["ciclo"] == "CRIA"
    assert projected["anos"][0]["compra_desmama_estimada"] == legacy["compra_desmama_estimada"]
    assert projected["anos"][0]["repoe_compra_desmama"] == legacy["repoe_compra_desmama"]
    _compare_years(
        projected["anos"][0],
        legacy,
        keys=(
            "total",
            "matrizes",
            "bezerros",
            "vendidos",
            "bois_vendidos",
            "matrizes_descartadas",
            "bezerras_vendidas",
            "machos_vendidos",
            "femeas_excedentes",
            "aumento_matrizes",
            "receita",
            "custo",
            "custo_manutencao",
            "custo_compra_desmama",
            "resultado",
            "bois_fim",
            "jovens_f_fim",
            "jovens_m_fim",
            "compras",
            "mortes",
        ),
    )
    _compare_years(
        projected["acumulado"],
        legacy | {"receita": legacy["receita"], "custo": legacy["custo"], "resultado": legacy["resultado"]},
        keys=("receita", "custo", "resultado"),
    )


def test_project_cria_replica_legacy_purchase_carry_forward(monkeypatch):
    state = _state(CRIA)
    params = _cria_parameters()
    params["repoe_compra_desmama"] = True
    monkeypatch.setattr(ml_engine, "_REPOR_COMPRA_DESMAMA", True)
    legacy = _legacy_years(
        CRIA,
        "CRIA",
        2,
        preco_arroba=330.0,
        custo_arroba=11.31,
        venda_bez_pct=PARAMS_POR_CICLO["CRIA"]["venda_bez_pct"],
    )

    projected = project_cria(state, params, years=2)

    assert projected["anos"][0]["repoe_compra_desmama"] is True
    assert projected["anos"][0]["compra_desmama_estimada"] == legacy[0]["compra_desmama_estimada"]
    assert projected["anos"][0]["custo_compra_desmama"] == pytest.approx(legacy[0]["custo_compra_desmama"], abs=1.0)
    assert projected["anos"][0]["total"] == legacy[0]["total"]
    assert projected["anos"][1]["total"] == legacy[1]["total"]
    assert projected["anos"][1]["jovens_f_fim"] == legacy[1]["jovens_f_fim"]
    assert projected["anos"][1]["jovens_m_fim"] == legacy[1]["jovens_m_fim"]


def test_project_recria_matches_legacy_characterization_and_pricing():
    state = _state(RECRIA)
    params = _recria_parameters()
    legacy = _legacy_year1(RECRIA, "RECRIA", preco_arroba=320.0, custo_arroba=119.0)

    projected = project_recria(state, params, years=1)

    assert projected["ciclo"] == "RECRIA"
    assert projected["anos"][0]["compras"] == legacy["compras"]
    _compare_years(
        projected["anos"][0],
        legacy,
        keys=(
            "total",
            "matrizes",
            "vendidos",
            "bois_vendidos",
            "custo_manutencao",
            "custo_reposicao",
            "resultado",
            "jovens_f_fim",
            "jovens_m_fim",
            "compras",
            "mortes",
            "ganho_arrobas_por_animal",
        ),
    )

    priced = project_recria(state, _recria_parameters(preco_bezerro_cab=2241.0), years=1)
    assert priced["anos"][0]["custo_reposicao"] == pytest.approx(440_560.66, abs=0.01)


def test_project_engorda_matches_legacy_and_uses_fractional_turns():
    state = _state(ENGORDA)
    params = _engorda_parameters()
    legacy = _legacy_year1(
        ENGORDA,
        "ENGORDA",
        preco_arroba=330.0,
        custo_arroba=17.21,
        ganho_peso_kg_dia=0.85,
    )

    projected = project_engorda(state, params, years=1)

    assert projected["ciclo"] == "ENGORDA"
    _compare_years(
        projected["anos"][0],
        legacy,
        keys=(
            "total",
            "vendidos",
            "bois_vendidos",
            "compras",
            "custo_manutencao",
            "custo_reposicao",
            "resultado",
            "arrobas_por_boi",
            "arrobas_ganho_por_boi",
            "lotes_por_ano",
            "ganho_peso_kg",
            "mortes",
        ),
    )
    assert projected["anos"][0]["lotes_por_ano"] == pytest.approx(2.70, abs=0.02)

    faster = project_engorda(state, _engorda_parameters(ganho_peso_kg_dia=1.28), years=1)
    assert faster["anos"][0]["lotes_por_ano"] > projected["anos"][0]["lotes_por_ano"]


def test_project_full_cycle_matches_legacy_and_never_double_counts_sales():
    state = _state(CICLO_COMPLETO)
    params = _full_cycle_parameters()
    legacy = _legacy_year1(
        CICLO_COMPLETO,
        "CICLO_COMPLETO",
        preco_arroba=320.0,
        custo_arroba=122.0,
    )

    projected = project_full_cycle(state, params, years=1)

    assert projected["ciclo"] == "CICLO_COMPLETO"
    _compare_years(
        projected["anos"][0],
        legacy,
        keys=(
            "total",
            "matrizes",
            "bezerros",
            "vendidos",
            "bois_vendidos",
            "matrizes_descartadas",
            "bezerras_vendidas",
            "machos_vendidos",
            "aumento_matrizes",
            "receita",
            "custo",
            "resultado",
            "bois_fim",
            "jovens_f_fim",
            "jovens_m_fim",
        ),
    )
    ano1 = projected["anos"][0]
    assert ano1["machos_vendidos"] == 0
    assert ano1["vendidos"] == (
        ano1["bois_vendidos"]
        + ano1["matrizes_descartadas"]
        + ano1["bezerras_vendidas"]
        + ano1["machos_vendidos"]
    )


def test_project_full_cycle_keeps_legacy_opening_mix_cost_when_phase_costs_differ():
    state = _state(CICLO_COMPLETO)
    params = _full_cycle_parameters()
    params.update(
        {
            "custo_arroba_cria": 40.0,
            "custo_arroba_recria": 80.0,
            "custo_arroba_engorda": 120.0,
        }
    )
    legacy = _legacy_years(
        CICLO_COMPLETO,
        "CICLO_COMPLETO",
        3,
        preco_arroba=320.0,
        custo_arroba=122.0,
        custo_arroba_cria=40.0,
        custo_arroba_recria=80.0,
        custo_arroba_engorda=120.0,
    )

    projected = project_full_cycle(state, params, years=3)

    for idx in range(3):
        _compare_years(
            projected["anos"][idx],
            legacy[idx],
            keys=(
                "total",
                "matrizes",
                "bezerros",
                "vendidos",
                "bois_vendidos",
                "matrizes_descartadas",
                "bezerras_vendidas",
                "machos_vendidos",
                "aumento_matrizes",
                "receita",
                "custo",
                "resultado",
                "bois_fim",
                "jovens_f_fim",
                "jovens_m_fim",
            ),
        )


@pytest.mark.parametrize(
    "system,projector,params,legacy_kwargs",
    [
        ("CRIA", project_cria, _cria_parameters(), {"preco_arroba": 330.0, "custo_arroba": 11.31}),
        ("RECRIA", project_recria, _recria_parameters(), {"preco_arroba": 320.0, "custo_arroba": 119.0}),
        ("ENGORDA", project_engorda, _engorda_parameters(), {"preco_arroba": 330.0, "custo_arroba": 17.21, "ganho_peso_kg_dia": 0.85}),
        ("CICLO_COMPLETO", project_full_cycle, _full_cycle_parameters(), {"preco_arroba": 320.0, "custo_arroba": 122.0}),
    ],
)
def test_project_production_dispatches_to_the_requested_system(system, projector, params, legacy_kwargs):
    state = _state(CRIA if system == "CRIA" else RECRIA if system == "RECRIA" else ENGORDA if system == "ENGORDA" else CICLO_COMPLETO)

    projected = project_production(state, system, params, years=1)
    direct = projector(state, params, years=1)
    legacy = _legacy_year1(
        state.values,
        system,
        **legacy_kwargs,
    )

    assert projected["ciclo"] == system
    assert projected["anos"][0]["total"] == direct["anos"][0]["total"]
    _compare_years(
        projected["anos"][0],
        legacy,
        keys=("total", "vendidos", "receita", "custo", "resultado"),
    )
