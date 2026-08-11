from __future__ import annotations


P_MATRIZES_CRIA = 0.18
RAZAO_MATRIZ_MADURA_CRIA = 0.50


def _share(indicators: dict, key: str) -> float:
    return float(indicators.get(key, 0.0)) / 100.0


def current_rule_metrics(indicators: dict) -> dict:
    total_animals = max(int(indicators.get("total_animals", 0)), 1)
    total_females = float(indicators.get("total_females", 0))

    p_matrizes = _share(indicators, "pct_matrices")
    p_young_males = _share(indicators, "pct_young_males")
    p_adult_males = _share(indicators, "pct_adult_males")
    p_calves = _share(indicators, "pct_calves")
    female_share = total_females / total_animals
    mature_matrix_ratio = float(indicators.get("mature_matrix_ratio", 0.0))

    full_cycle_score = (
        int(p_matrizes > P_MATRIZES_CRIA)
        + int(p_young_males > 0.10)
        + int(p_adult_males > 0.10)
        + int(p_calves > 0.12)
    )

    return {
        "p_matrizes": p_matrizes,
        "p_young_males": p_young_males,
        "p_adult_males": p_adult_males,
        "p_calves": p_calves,
        "female_share": female_share,
        "mature_matrix_ratio": mature_matrix_ratio,
        "full_cycle_score": full_cycle_score,
    }


def identify_system(indicators: dict) -> str:
    metrics = current_rule_metrics(indicators)

    if metrics["full_cycle_score"] >= 4:
        return "CICLO_COMPLETO"

    if (
        metrics["p_matrizes"] >= P_MATRIZES_CRIA
        and metrics["mature_matrix_ratio"] >= RAZAO_MATRIZ_MADURA_CRIA
        and metrics["p_calves"] >= 0.20
    ):
        return "CRIA"

    if (
        metrics["p_adult_males"] >= 0.10
        and metrics["p_matrizes"] < P_MATRIZES_CRIA
        and metrics["female_share"] < 0.35
    ):
        return "ENGORDA"

    return "RECRIA"
