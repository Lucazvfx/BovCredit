import pytest

from ml_engine import calcular_indicadores
from services.engine.contracts import HerdState
from services.livestock_engine import analyze_herd, calculate_herd_indicators, explain_system
from services.livestock_engine.rules import current_rule_metrics
from services.parametros_zootecnicos import NATALIDADE_PCT


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

    assert indicators | {
        "p_matrizes": round(indicators["p_matrizes"], 3),
        "p_mac_13_24": round(indicators["p_mac_13_24"], 3),
        "p_bois": round(indicators["p_bois"], 3),
        "p_bez": round(indicators["p_bez"], 3),
        "p_fem_total": round(indicators["p_fem_total"], 3),
        "p_garrotes_25_36": round(indicators["p_garrotes_25_36"], 3),
        "intensidade_engorda": round(indicators["intensidade_engorda"], 3),
        "intensidade_cria": round(indicators["intensidade_cria"], 3),
    } == {
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
        "p_matrizes": 0.388,
        "p_mac_13_24": 0.138,
        "p_bois": 0.086,
        "p_bez": 0.526,
        "p_fem_total": 0.69,
        "p_garrotes_25_36": 0.034,
        "intensidade_engorda": 0.0,
        "intensidade_cria": 0.158,
        "indice_ciclo": 3,
        "bois_vendidos_informados": False,
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


def test_current_rule_metrics_match_live_classifier_signal_names_and_values():
    indicators = calculate_herd_indicators([12, 10, 8, 9, 15, 7, 5, 4, 40, 6])

    metrics = current_rule_metrics(indicators)

    assert metrics == {
        "p_matrizes": pytest.approx(45 / 116),
        "p_mac_13_24": pytest.approx(16 / 116),
        "p_bois": pytest.approx(10 / 116),
        "p_bez": pytest.approx(61 / 116),
        "p_fem_total": pytest.approx(80 / 116),
        "p_garrotes_25_36": pytest.approx(4 / 116),
        "intensidade_engorda": 0.0,
        "intensidade_cria": pytest.approx((61 * 0.3) / 116),
        "indice_ciclo": 3,
        "mature_matrix_ratio": 8.0,
        "bois_vendidos_informados": False,
    }


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
        "p_matrizes",
        "p_bez",
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
            "tipo": "RECRIA",
            "tipo_modelo": "ENGORDA",
            "confianca_ml": 88.0,
            "probabilidades": {"ENGORDA": 88.0, "RECRIA": 10.0},
        },
    )

    assert analysis["system"] == "RECRIA"
    assert analysis["ml_predicted_system"] == "ENGORDA"
    assert analysis["explanation"]["ml_evidence"]["predicted_system"] == "ENGORDA"
    assert analysis["explanation"]["deterministic_evidence"][0]["source"] == "deterministic"


def test_analyze_herd_applies_live_no_sale_post_processing_to_raw_model_signal():
    state = HerdState(
        values=[20, 18, 40, 42, 65, 70, 55, 20, 110, 45],
        source="MANUAL",
        farm_id=4,
        metadata={},
    )

    analysis = analyze_herd(
        state,
        ml_result={
            "tipo_modelo": "ENGORDA",
            "confianca_ml": 91.0,
            "probabilidades": {
                "ENGORDA": 91.0,
                "CRIA_RECRIA": 72.0,
                "CRIA": 61.0,
                "RECRIA": 44.0,
            },
            "dados_faltantes": ["bois_vendidos"],
        },
    )

    assert analysis["system"] == "CRIA_RECRIA"
    assert analysis["ml_predicted_system"] == "ENGORDA"


def test_analyze_herd_preserves_live_mixed_cycle_metadata():
    state = HerdState(
        values=[80, 70, 60, 60, 50, 250, 30, 5, 200, 5],
        source="MANUAL",
        farm_id=5,
        metadata={},
    )

    analysis = analyze_herd(
        state,
        ml_result={
            "tipo": "CRIA",
            "tipo_modelo": "CRIA",
            "probabilidades": {
                "CRIA": 55.0,
                "RECRIA": 35.0,
                "ENGORDA": 5.0,
                "CICLO_COMPLETO": 5.0,
            },
            "tipo_secundario": "RECRIA",
            "combinacao": "CRIA+RECRIA",
            "confianca_secundaria": 35.0,
        },
    )

    assert analysis["system"] == "CRIA"
    assert analysis["secondary_system"] == "RECRIA"
    assert analysis["system_combination"] == "CRIA+RECRIA"
    assert analysis["secondary_confidence"] == 35.0


def test_explain_system_uses_live_cycle_score_signals_for_ciclo_completo():
    state = HerdState(
        values=[300, 280, 200, 180, 150, 140, 120, 90, 260, 110],
        source="MANUAL",
        farm_id=2,
        metadata={},
    )

    indicators = calculate_herd_indicators(state.values)
    explanation = explain_system("CICLO_COMPLETO", indicators)

    assert {item["key"] for item in explanation["deterministic_evidence"]} == {
        "p_matrizes",
        "p_mac_13_24",
        "p_bois",
        "p_bez",
        "indice_ciclo",
    }
    assert explanation["ml_evidence"] is None


@pytest.mark.parametrize(
    "label",
    [
        "CRIA",
        "RECRIA",
        "ENGORDA",
        "CICLO_COMPLETO",
        "CRIA_RECRIA",
        "RECRIA_ENGORDA",
    ],
)
def test_analyze_herd_preserves_all_six_live_classifier_labels(label):
    state = HerdState(
        values=[20, 18, 40, 42, 65, 70, 55, 20, 110, 45],
        source="MANUAL",
        farm_id=3,
        metadata={},
    )

    analysis = analyze_herd(
        state,
        ml_result={
            "tipo": label,
            "tipo_modelo": label,
            "confianca_ml": 77.0,
            "probabilidades": {label: 77.0},
        },
    )

    assert analysis["system"] == label
    assert analysis["ml_predicted_system"] == label


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
