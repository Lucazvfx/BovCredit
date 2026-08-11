from __future__ import annotations

from .rules import (
    P_MATRIZES_CRIA,
    RAZAO_MATRIZ_MADURA_CRIA,
    current_rule_metrics,
)


def _deterministic_item(key: str, value: float, message: str) -> dict:
    return {
        "source": "deterministic",
        "key": key,
        "value": value,
        "message": message,
    }


def _ml_evidence(ml_result: dict | None) -> dict | None:
    if not ml_result:
        return None

    predicted_system = (
        ml_result.get("tipo_modelo")
        or ml_result.get("tipo")
        or ml_result.get("classificacao")
    )
    probabilities = dict(ml_result.get("probabilidades") or {})
    confidence = ml_result.get("confianca_ml")
    if confidence is None and predicted_system in probabilities:
        confidence = probabilities[predicted_system]

    return {
        "source": "ml",
        "predicted_system": predicted_system,
        "confidence": confidence,
        "probabilities": probabilities,
    }


def explain_system(system: str, indicators: dict, ml_result: dict | None = None) -> dict:
    metrics = current_rule_metrics(indicators)
    evidence: list[dict] = []

    if system == "CRIA":
        evidence.extend(
            [
                _deterministic_item(
                    "pct_matrices",
                    indicators["pct_matrices"],
                    (
                        f"Matrizes em {indicators['pct_matrices']}% do rebanho "
                        f"(limiar atual {P_MATRIZES_CRIA:.0%}) sustentam base de cria."
                    ),
                ),
                _deterministic_item(
                    "pct_calves",
                    indicators["pct_calves"],
                    f"Animais até 24 meses somam {indicators['pct_calves']}% e reforçam perfil de cria.",
                ),
                _deterministic_item(
                    "mature_matrix_ratio",
                    indicators["mature_matrix_ratio"],
                    (
                        f"Razão de matrizes maduras em {indicators['mature_matrix_ratio']}"
                        f" (mínimo atual {RAZAO_MATRIZ_MADURA_CRIA:.2f})."
                    ),
                ),
            ]
        )
    elif system == "ENGORDA":
        evidence.extend(
            [
                _deterministic_item(
                    "pct_adult_males",
                    indicators["pct_adult_males"],
                    "Concentração de animais terminados sustenta perfil de engorda.",
                ),
                _deterministic_item(
                    "pct_matrices",
                    indicators["pct_matrices"],
                    "Baixa participação de matrizes afasta base reprodutiva.",
                ),
                _deterministic_item(
                    "female_share",
                    round(metrics["female_share"] * 100, 1),
                    "Participação feminina contida reforça leitura de terminação.",
                ),
            ]
        )
    elif system == "CICLO_COMPLETO":
        evidence.extend(
            [
                _deterministic_item(
                    "pct_matrices",
                    indicators["pct_matrices"],
                    "Matrizes relevantes mostram base reprodutiva ativa.",
                ),
                _deterministic_item(
                    "pct_young_males",
                    indicators["pct_young_males"],
                    "Machos jovens relevantes mostram etapa de recria ativa.",
                ),
                _deterministic_item(
                    "pct_adult_males",
                    indicators["pct_adult_males"],
                    "Animais terminados relevantes mostram etapa de engorda ativa.",
                ),
                _deterministic_item(
                    "pct_calves",
                    indicators["pct_calves"],
                    (
                        f"Composição mista atinge score {metrics['full_cycle_score']}/4 "
                        "pelos critérios atuais do ciclo completo."
                    ),
                ),
            ]
        )
    else:
        evidence.extend(
            [
                _deterministic_item(
                    "pct_young_males",
                    indicators["pct_young_males"],
                    "Concentração de animais jovens sustenta perfil de recria.",
                ),
                _deterministic_item(
                    "pct_recria",
                    indicators["pct_recria"],
                    "Faixa de recria relevante indica permanência na fase intermediária.",
                ),
                _deterministic_item(
                    "pct_matrices",
                    indicators["pct_matrices"],
                    "Base reprodutiva insuficiente para tratar o sistema como cria.",
                ),
            ]
        )

    return {
        "system": system,
        "deterministic_evidence": evidence,
        "ml_evidence": _ml_evidence(ml_result),
        "missing_data": list((ml_result or {}).get("dados_faltantes") or []),
    }
