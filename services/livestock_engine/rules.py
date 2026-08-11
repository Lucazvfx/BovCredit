from __future__ import annotations


P_MATRIZES_CRIA = 0.18
RAZAO_MATRIZ_MADURA_CRIA = 0.50

_KNOWN_SYSTEMS = frozenset(
    {
        "CRIA",
        "RECRIA",
        "ENGORDA",
        "CICLO_COMPLETO",
        "CRIA_RECRIA",
        "RECRIA_ENGORDA",
    }
)

_PARES_VALIDOS = frozenset(
    {
        ("CRIA", "RECRIA"),
        ("RECRIA", "CRIA"),
        ("RECRIA", "ENGORDA"),
        ("ENGORDA", "RECRIA"),
        ("CRIA", "ENGORDA"),
        ("ENGORDA", "CRIA"),
    }
)

_MISTO_PROB_MIN = 25.0
_MISTO_GAP_MAX = 50.0


def current_rule_metrics(indicators: dict) -> dict:
    return {
        "p_matrizes": float(indicators.get("p_matrizes", 0.0)),
        "p_mac_13_24": float(indicators.get("p_mac_13_24", 0.0)),
        "p_bois": float(indicators.get("p_bois", 0.0)),
        "p_bez": float(indicators.get("p_bez", 0.0)),
        "p_fem_total": float(indicators.get("p_fem_total", 0.0)),
        "p_garrotes_25_36": float(indicators.get("p_garrotes_25_36", 0.0)),
        "intensidade_engorda": float(indicators.get("intensidade_engorda", 0.0)),
        "intensidade_cria": float(indicators.get("intensidade_cria", 0.0)),
        "indice_ciclo": int(indicators.get("indice_ciclo", 0)),
        "mature_matrix_ratio": float(indicators.get("mature_matrix_ratio", 0.0)),
        "bois_vendidos_informados": bool(indicators.get("bois_vendidos_informados", False)),
    }


def _ml_final_system(ml_result: dict | None) -> str | None:
    if not ml_result:
        return None
    label = ml_result.get("tipo") or ml_result.get("classificacao")
    if label in _KNOWN_SYSTEMS:
        return label
    return None


def _ml_model_system(ml_result: dict | None) -> str | None:
    if not ml_result:
        return None
    label = (
        ml_result.get("tipo_modelo")
        or ml_result.get("tipo")
        or ml_result.get("classificacao")
    )
    if label in _KNOWN_SYSTEMS:
        return label
    return None


def _probabilities(ml_result: dict | None) -> dict[str, float]:
    if not ml_result:
        return {}
    return {
        label: float(probability)
        for label, probability in dict(ml_result.get("probabilidades") or {}).items()
        if label in _KNOWN_SYSTEMS
    }


def _best_system(candidates: tuple[str, ...], probabilities: dict[str, float]) -> str:
    return max(candidates, key=lambda label: probabilities.get(label, 0.0))


def _second_best_non_cycle(probabilities: dict[str, float]) -> str | None:
    ordered = sorted(probabilities, key=lambda label: probabilities[label])
    for label in reversed(ordered):
        if label != "CICLO_COMPLETO" and label in _KNOWN_SYSTEMS:
            return label
    return None


def _supports_engorda_pura(metrics: dict) -> bool:
    return (
        metrics["p_matrizes"] < 0.02
        and metrics["p_fem_total"] < 0.10
        and metrics["p_garrotes_25_36"] > 0.08
    )


def _supports_indice_ciclo_completo(metrics: dict) -> bool:
    return metrics["indice_ciclo"] >= 4 and metrics["intensidade_engorda"] > 0.05


def _supports_rescue_ciclo_completo(metrics: dict, model_label: str | None) -> bool:
    return (
        model_label == "CICLO_COMPLETO"
        and metrics["indice_ciclo"] >= 3
        and metrics["p_bois"] > 0.08
        and metrics["p_matrizes"] > 0.20
        and metrics["p_bez"] > 0.20
    )


def _supports_rescue_ciclo_completo_from_cria(metrics: dict, model_label: str | None) -> bool:
    return (
        model_label == "CRIA"
        and metrics["indice_ciclo"] >= 3
        and metrics["p_bois"] > 0.08
        and metrics["p_matrizes"] > 0.20
        and metrics["p_bez"] > 0.20
    )


def _supports_rescue_engorda(metrics: dict, model_label: str | None) -> bool:
    return model_label in {"ENGORDA", "RECRIA_ENGORDA"} and metrics["p_bois"] > 0.45


def _cria_guard_reclassifies(system: str, metrics: dict) -> bool:
    return (
        system in {"CRIA", "CRIA_RECRIA"}
        and (
            metrics["p_matrizes"] < P_MATRIZES_CRIA
            or metrics["mature_matrix_ratio"] < RAZAO_MATRIZ_MADURA_CRIA
        )
    )


def _supports_ciclo_completo_inferido(metrics: dict, model_label: str | None) -> bool:
    return (
        not metrics["bois_vendidos_informados"]
        and model_label == "CICLO_COMPLETO"
        and metrics["mature_matrix_ratio"] >= 1.0
    )


def _composicao_suporta(
    principal: str,
    secundario: str,
    metrics: dict,
) -> bool:
    pair = frozenset([principal, secundario])

    if pair == frozenset(["CRIA", "RECRIA"]):
        return metrics["p_matrizes"] > 0.10 and metrics["p_mac_13_24"] > 0.05

    if pair == frozenset(["RECRIA", "ENGORDA"]):
        return metrics["p_mac_13_24"] > 0.05 and (
            metrics["p_bois"] > 0.05 or metrics["intensidade_engorda"] > 0.05
        )

    if pair == frozenset(["CRIA", "ENGORDA"]):
        return (
            metrics["p_matrizes"] > 0.10
            and metrics["p_bois"] > 0.05
            and metrics["p_mac_13_24"] < 0.15
        )

    return False


def mixed_cycle_evidence(
    system: str,
    indicators: dict,
    ml_result: dict | None = None,
) -> dict | None:
    if ml_result:
        secondary = ml_result.get("tipo_secundario")
        combination = ml_result.get("combinacao")
        if secondary and combination and combination != system:
            return {
                "tipo_secundario": secondary,
                "combinacao": combination,
                "confianca_secundaria": float(ml_result.get("confianca_secundaria", 0.0)),
            }

    if system in {"CICLO_COMPLETO", "CRIA_RECRIA", "RECRIA_ENGORDA"}:
        return None

    probabilities = _probabilities(ml_result)
    candidates = [
        (label, probability)
        for label, probability in probabilities.items()
        if label != system and label != "CICLO_COMPLETO"
    ]
    if not candidates:
        return None

    secondary, secondary_probability = max(candidates, key=lambda item: item[1])
    if secondary_probability < _MISTO_PROB_MIN:
        return None
    if (probabilities.get(system, 0.0) - secondary_probability) > _MISTO_GAP_MAX:
        return None
    if (system, secondary) not in _PARES_VALIDOS:
        return None
    if not _composicao_suporta(system, secondary, current_rule_metrics(indicators)):
        return None

    return {
        "tipo_secundario": secondary,
        "combinacao": "+".join(sorted([system, secondary])),
        "confianca_secundaria": round(float(secondary_probability), 1),
    }


def identify_system(indicators: dict, ml_result: dict | None = None) -> str:
    final_system = _ml_final_system(ml_result)
    if final_system is not None:
        return final_system

    metrics = current_rule_metrics(indicators)
    model_system = _ml_model_system(ml_result)
    probabilities = _probabilities(ml_result)

    if model_system is None and probabilities:
        model_system = _best_system(tuple(probabilities), probabilities)

    if _supports_ciclo_completo_inferido(metrics, model_system):
        return "CICLO_COMPLETO"
    if _supports_engorda_pura(metrics):
        return "ENGORDA"
    if _supports_indice_ciclo_completo(metrics):
        return "CICLO_COMPLETO"

    if model_system in {"ENGORDA", "CICLO_COMPLETO"} and metrics["intensidade_engorda"] < 0.10:
        if _supports_rescue_ciclo_completo(metrics, model_system):
            return "CICLO_COMPLETO"
        if _supports_rescue_engorda(metrics, model_system):
            return model_system
        system = _best_system(("CRIA", "RECRIA", "CRIA_RECRIA"), probabilities)
        return "RECRIA" if _cria_guard_reclassifies(system, metrics) else system

    if model_system in _KNOWN_SYSTEMS and metrics["intensidade_engorda"] < 0.10:
        if _supports_rescue_ciclo_completo_from_cria(metrics, model_system):
            return "CICLO_COMPLETO"
        return "RECRIA" if _cria_guard_reclassifies(model_system, metrics) else model_system

    if model_system == "CICLO_COMPLETO" and metrics["indice_ciclo"] <= 1:
        fallback = _second_best_non_cycle(probabilities)
        if fallback is None:
            fallback = "CRIA" if metrics["p_matrizes"] >= P_MATRIZES_CRIA else "RECRIA"
        return "RECRIA" if _cria_guard_reclassifies(fallback, metrics) else fallback

    if model_system in _KNOWN_SYSTEMS:
        return "RECRIA" if _cria_guard_reclassifies(model_system, metrics) else model_system

    if metrics["p_matrizes"] >= P_MATRIZES_CRIA and metrics["mature_matrix_ratio"] >= RAZAO_MATRIZ_MADURA_CRIA:
        return "CRIA"
    return "RECRIA"
