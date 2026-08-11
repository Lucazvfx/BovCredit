import pytest

from services.parametros_zootecnicos import (
    APROVEITAMENTO_PRENHEZ_PCT,
    GANHO_ARROBA_MES,
    MORTALIDADE_PCT,
    NATALIDADE_PCT,
    PESO_BEZERRA_ARR,
    PESO_BOI_ARR,
    PESO_GARROTE_ARR,
    PESO_VACA_ARR,
    PRENHEZ_PCT,
    RELACAO_FM,
    RENDIMENTO_CARCACA_PCT,
    midpoint,
    natalidade_de_prenhez,
    taxa_desmama_efetiva,
)
from services.proveniencia import DECLARADO, REFERENCIA
from services.engine.parameter_registry import Parameter, get_parameter, resolve_parameters


def test_registry_keeps_existing_defaults_for_current_parameters():
    expected = {
        ("CRIA", "natalidade_pct"): float(NATALIDADE_PCT),
        ("CRIA", "mortalidade_pct"): float(MORTALIDADE_PCT),
        ("CRIA", "relacao_fm"): float(RELACAO_FM),
        ("RECRIA", "ganho_arroba_mes"): float(GANHO_ARROBA_MES),
        ("ENGORDA", "rendimento_carcaca_pct"): float(RENDIMENTO_CARCACA_PCT),
        ("ENGORDA", "peso_boi_arr"): float(PESO_BOI_ARR),
        ("ENGORDA", "peso_vaca_arr"): float(PESO_VACA_ARR),
        ("RECRIA", "peso_garrote_arr"): float(PESO_GARROTE_ARR),
        ("RECRIA", "peso_bezerra_arr"): float(PESO_BEZERRA_ARR),
    }

    actual = {
        key: float(get_parameter(name, system).value)
        for (system, name), key in ((item, item) for item in expected)
    }

    assert actual == expected


def test_registry_metadata_carries_source_year_unit_system_and_range():
    boi = get_parameter("peso_boi_arr", "ENGORDA")

    assert isinstance(boi, Parameter)
    assert boi.source == "GEP Araguaia / Fazenda Alvorada"
    assert boi.reference_year == 2025
    assert boi.unit == "@ carcaca"
    assert boi.system == "ENGORDA"
    assert boi.plausible_range == (float(PESO_BOI_ARR), float(PESO_BOI_ARR))


def test_resolve_parameters_accepts_valid_override_and_marks_it_declared():
    resolved = resolve_parameters({"natalidade_pct": 72.0}, system="CRIA")

    assert resolved["natalidade_pct"] == 72.0
    assert resolved["natalidade_pct"].origem == DECLARADO
    assert resolved["mortalidade_pct"].origem == REFERENCIA
    assert resolved["mortalidade_pct"] == MORTALIDADE_PCT


def test_resolve_parameters_rejects_unknown_names_and_out_of_range_values():
    with pytest.raises(KeyError, match="unknown parameter"):
        resolve_parameters({"nao_existe": 1.0}, system="CRIA")

    with pytest.raises(ValueError, match="natalidade_pct.*55.0.*80.0"):
        resolve_parameters({"natalidade_pct": 90.0}, system="CRIA")


def test_legacy_public_functions_keep_current_results():
    assert midpoint(55.0, 75.0) == 65.0
    assert natalidade_de_prenhez(PRENHEZ_PCT) == pytest.approx(
        float(PRENHEZ_PCT) * float(APROVEITAMENTO_PRENHEZ_PCT) / 100.0
    )
    assert taxa_desmama_efetiva(70.0, 7.0) == pytest.approx(0.651, abs=0.001)
