from __future__ import annotations

from services.engine.contracts import HerdState
from services.parametros_zootecnicos import NATALIDADE_PCT

from .explanations import explain_system
from .rules import identify_system


def _round_pct(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 1)


def calculate_herd_indicators(values: list[float] | tuple[float, ...]) -> dict:
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
        "pct_calves": _round_pct(sum(herd[:6]), denominator),
        "mature_matrix_ratio": mature_matrix_ratio,
    }


def analyze_herd(state: HerdState, *, ml_result: dict | None = None) -> dict:
    indicators = calculate_herd_indicators(state.values)
    system = identify_system(indicators)
    explanation = explain_system(system, indicators, ml_result)
    ml_evidence = explanation["ml_evidence"]

    return {
        "system": system,
        "indicators": indicators,
        "explanation": explanation,
        "ml_predicted_system": None if ml_evidence is None else ml_evidence["predicted_system"],
        "model_probabilities": None if ml_evidence is None else ml_evidence["probabilities"],
    }
