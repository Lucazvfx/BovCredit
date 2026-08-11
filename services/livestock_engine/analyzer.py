from __future__ import annotations

from services.engine.contracts import HerdState
from services.parametros_zootecnicos import NATALIDADE_PCT

from .explanations import explain_system
from .rules import identify_system


def _round_pct(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 1)


def _share(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _calculate_herd_indicators(
    values: list[float] | tuple[float, ...],
    *,
    bois_vendidos: float | None = None,
    bezerros_vendidos: float | None = None,
) -> dict:
    herd = [float(value) for value in values]
    total = sum(herd)
    denominator = total or 1.0

    females_0_24 = herd[0] + herd[2] + herd[4]
    males_0_24 = herd[1] + herd[3] + herd[5]
    matrices = herd[6] + herd[8]
    adult_males = herd[7] + herd[9]
    cria = herd[0] + herd[1] + herd[2] + herd[3]
    recria = herd[4] + herd[5]
    adults = matrices + adult_males
    total_females = females_0_24 + matrices
    total_males = males_0_24 + adult_males
    bezerros_0_24 = females_0_24 + males_0_24
    bois_regra = 0.0 if bois_vendidos is None else float(bois_vendidos)
    bezerros_regra = bezerros_0_24 * 0.3 if bezerros_vendidos is None else float(bezerros_vendidos)
    p_matrizes = _share(matrices, denominator)
    p_mac_13_24 = _share(herd[3] + herd[5], denominator)
    p_bois = _share(adult_males, denominator)
    p_bez = _share(bezerros_0_24, denominator)
    indice_ciclo = (
        int(p_matrizes > 0.18)
        + int(p_mac_13_24 > 0.10)
        + int(p_bois > 0.10)
        + int(p_bez > 0.12)
    )

    if herd[6] > 0:
        mature_matrix_ratio = round(herd[8] / herd[6], 2)
    elif herd[8] > 0:
        mature_matrix_ratio = float("inf")
    else:
        mature_matrix_ratio = 0.0

    return {
        "total_animals": int(total),
        "total_females": int(total_females),
        "total_males": int(total_males),
        "females_0_24_months": int(females_0_24),
        "males_0_24_months": int(males_0_24),
        "matrices": int(matrices),
        "adult_females": int(matrices),
        "adult_males": int(adult_males),
        "bois": int(adult_males),
        "cria": int(cria),
        "recria": int(recria),
        "adults": int(adults),
        "pct_cria": _round_pct(cria, denominator),
        "pct_recria": _round_pct(recria, denominator),
        "pct_adults": _round_pct(adults, denominator),
        "pct_matrices": _round_pct(matrices, denominator),
        "pct_adult_males": _round_pct(adult_males, denominator),
        "female_male_ratio": round(total_females / max(total_males, 1.0), 2),
        "matrix_bull_ratio": round(matrices / max(adult_males, 1.0), 2),
        "estimated_calves": int(matrices * NATALIDADE_PCT / 100),
        "pct_young_males": _round_pct(herd[3] + herd[5], denominator),
        "pct_calves": _round_pct(bezerros_0_24, denominator),
        "mature_matrix_ratio": mature_matrix_ratio,
        "p_matrizes": p_matrizes,
        "p_mac_13_24": p_mac_13_24,
        "p_bois": p_bois,
        "p_bez": p_bez,
        "p_fem_total": _share(total_females, denominator),
        "p_garrotes_25_36": _share(herd[7], denominator),
        "intensidade_engorda": _share(bois_regra, denominator),
        "intensidade_cria": _share(bezerros_regra, denominator),
        "indice_ciclo": indice_ciclo,
        "bois_vendidos_informados": bois_vendidos is not None,
    }


def calculate_herd_indicators(values: list[float] | tuple[float, ...]) -> dict:
    return _calculate_herd_indicators(values)


def analyze_herd(state: HerdState, *, ml_result: dict | None = None) -> dict:
    metadata = dict(state.metadata)
    indicators = _calculate_herd_indicators(
        state.values,
        bois_vendidos=metadata.get("bois_vendidos"),
        bezerros_vendidos=metadata.get("bezerros_vendidos"),
    )
    system = identify_system(indicators, ml_result)
    explanation = explain_system(system, indicators, ml_result)
    ml_evidence = explanation["ml_evidence"]
    mixed = explanation["mixed_cycle"]

    return {
        "system": system,
        "indicators": indicators,
        "explanation": explanation,
        "ml_predicted_system": None if ml_evidence is None else ml_evidence["predicted_system"],
        "model_probabilities": None if ml_evidence is None else ml_evidence["probabilities"],
        "secondary_system": None if mixed is None else mixed["tipo_secundario"],
        "system_combination": system if mixed is None else mixed["combinacao"],
        "secondary_confidence": 0.0 if mixed is None else mixed["confianca_secundaria"],
    }
