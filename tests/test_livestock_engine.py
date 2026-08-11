import pytest

from ml_engine import calcular_indicadores
from services.engine.contracts import HerdState
from services.parametros_zootecnicos import NATALIDADE_PCT
from services.livestock_engine import analyze_herd, calculate_herd_indicators, explain_system


def _legacy_projection(indicators: dict) -> dict:
    return {
        "total": indicators["total_animals"],
        "total_femeas": indicators["total_females"],
        "total_machos": indicators["total_males"],
        "femeas_024": indicators["females_0_24_months"],
        "machos_024": indicators["males_0_24_months"],
        "matrizes": indicators["matrices"],
        "bois": indicators["adult_males"],
        "fem_adultas": indicators["adult_females"],
        "mac_adultos": indicators["adult_males"],
        "cria": indicators["cria"],
        "recria": indicators["recria"],
        "adultos": indicators["adults"],
        "pct_cria": indicators["pct_cria"],
        "pct_recria": indicators["pct_recria"],
        "pct_adultos": indicators["pct_adults"],
        "pct_matrizes": indicators["pct_matrices"],
        "pct_mac_adultos": indicators["pct_adult_males"],
        "ratio_fm": indicators["female_male_ratio"],
        "bezerros_est": indicators["estimated_calves"],
    }


def test_calculate_herd_indicators_preserves_totals_percentages_and_ratios():
    indicators = calculate_herd_indicators([12, 10, 8, 9, 15, 7, 5, 4, 40, 6])

    assert indicators == {
        "total_animals": 116,
        "total_females": 80,
        "total_males": 36,
        "females_0_24_months": 35,
        "males_0_24_months": 26,
        "matrices": 45,
        "adult_females": 45,
        "adult_males": 10,
        "bois": 10,
        "cria": 39,
        "recria": 22,
        "adults": 55,
        "pct_cria": 33.6,
        "pct_recria": 19.0,
        "pct_adults": 47.4,
        "pct_matrices": 38.8,
        "pct_adult_males": 8.6,
        "female_male_ratio": 2.22,
        "matrix_bull_ratio": 4.5,
        "estimated_calves": int(45 * NATALIDADE_PCT / 100),
        "pct_young_males": 13.8,
        "pct_calves": 52.6,
        "mature_matrix_ratio": 8.0,
    }


@pytest.mark.parametrize(
    ("values", "expected_ratio_fm", "expected_ratio_matrix_bull"),
    [
        ([0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 0.0, 0.0),
        ([0, 0, 0, 0, 0, 0, 0, 0, 70, 0], 70.0, 70.0),
    ],
)
def test_calculate_herd_indicators_is_zero_safe(
    values, expected_ratio_fm, expected_ratio_matrix_bull
):
    indicators = calculate_herd_indicators(values)

    assert indicators["pct_cria"] == 0.0
    assert indicators["pct_recria"] == 0.0
    assert indicators["pct_adults"] in (0.0, 100.0)
    assert indicators["female_male_ratio"] == expected_ratio_fm
    assert indicators["matrix_bull_ratio"] == expected_ratio_matrix_bull
    assert indicators["estimated_calves"] == int(indicators["matrices"] * NATALIDADE_PCT / 100)


def test_explain_system_separates_deterministic_ml_and_missing_data():
    indicators = calculate_herd_indicators([150, 140, 80, 70, 20, 20, 90, 10, 220, 20])

    explanation = explain_system(
        "CRIA",
        indicators,
        {
            "tipo": "RECRIA",
            "tipo_modelo": "RECRIA",
            "confianca_ml": 61.0,
            "probabilidades": {"RECRIA": 61.0, "CRIA": 31.0},
            "dados_faltantes": ["bois_vendidos"],
        },
    )

    assert explanation["system"] == "CRIA"
    assert explanation["missing_data"] == ["bois_vendidos"]
    assert [item["source"] for item in explanation["deterministic_evidence"]] == [
        "deterministic",
        "deterministic",
        "deterministic",
    ]
    assert {item["key"] for item in explanation["deterministic_evidence"]} == {
        "pct_matrices",
        "pct_calves",
        "mature_matrix_ratio",
    }
    assert explanation["ml_evidence"] == {
        "source": "ml",
        "predicted_system": "RECRIA",
        "confidence": 61.0,
        "probabilities": {"RECRIA": 61.0, "CRIA": 31.0},
    }


def test_analyze_herd_keeps_ml_as_evidence_not_deterministic_fact():
    state = HerdState(
        values=[10, 10, 80, 90, 320, 340, 20, 25, 10, 15],
        source="MANUAL",
        farm_id=1,
        metadata={},
    )

    analysis = analyze_herd(
        state,
        ml_result={
            "tipo": "ENGORDA",
            "tipo_modelo": "ENGORDA",
            "confianca_ml": 88.0,
            "probabilidades": {"ENGORDA": 88.0, "RECRIA": 10.0},
        },
    )

    assert analysis["system"] == "RECRIA"
    assert analysis["ml_predicted_system"] == "ENGORDA"
    assert analysis["explanation"]["ml_evidence"]["predicted_system"] == "ENGORDA"
    assert analysis["explanation"]["deterministic_evidence"][0]["source"] == "deterministic"


def test_analyze_herd_identifies_supported_full_cycle_composition():
    state = HerdState(
        values=[300, 280, 200, 180, 150, 140, 120, 90, 260, 110],
        source="MANUAL",
        farm_id=2,
        metadata={},
    )

    analysis = analyze_herd(state)

    assert analysis["system"] == "CICLO_COMPLETO"
    assert {item["key"] for item in analysis["explanation"]["deterministic_evidence"]} == {
        "pct_matrices",
        "pct_young_males",
        "pct_adult_males",
        "pct_calves",
    }
    assert analysis["explanation"]["ml_evidence"] is None


@pytest.mark.parametrize(
    "values",
    [
        [12, 10, 8, 9, 15, 7, 5, 4, 40, 6],
        [0, 0, 0, 0, 0, 0, 0, 0, 70, 4],
        [300, 280, 563, 187, 1105, 1344, 298, 80, 593, 39],
    ],
)
def test_ml_engine_wrapper_stays_compatible_with_legacy_indicator_shape(values):
    expected = _legacy_projection(calculate_herd_indicators(values))

    assert calcular_indicadores(values) == expected
