from __future__ import annotations

from .rules import (
    P_MATRIZES_CRIA,
    RAZAO_MATRIZ_MADURA_CRIA,
    current_rule_metrics,
    mixed_cycle_evidence,
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
                    "p_matrizes",
                    metrics["p_matrizes"],
                    f"Matrizes em {metrics['p_matrizes']:.1%} do rebanho sustentam a base de cria (limiar {P_MATRIZES_CRIA:.0%}).",
                ),
                _deterministic_item(
                    "p_bez",
                    metrics["p_bez"],
                    f"Bezerros de 0-24 meses somam {metrics['p_bez']:.1%} e reforcam o perfil de cria.",
                ),
                _deterministic_item(
                    "mature_matrix_ratio",
                    metrics["mature_matrix_ratio"],
                    f"Razao de matrizes maduras em {metrics['mature_matrix_ratio']} mantem o corte atual de {RAZAO_MATRIZ_MADURA_CRIA:.2f}.",
                ),
            ]
        )
    elif system == "CRIA_RECRIA":
        evidence.extend(
            [
                _deterministic_item(
                    "p_matrizes",
                    metrics["p_matrizes"],
                    "Base reprodutiva presente sustenta a parte de cria do sistema misto.",
                ),
                _deterministic_item(
                    "p_mac_13_24",
                    metrics["p_mac_13_24"],
                    "Machos de 13-24 meses relevantes sustentam a parte de recria do sistema misto.",
                ),
                _deterministic_item(
                    "p_bez",
                    metrics["p_bez"],
                    "Coorte jovem relevante indica continuidade entre cria e recria.",
                ),
            ]
        )
    elif system == "ENGORDA":
        evidence.extend(
            [
                _deterministic_item(
                    "p_matrizes",
                    metrics["p_matrizes"],
                    "Baixa participacao de matrizes acompanha a regra de engorda pura.",
                ),
                _deterministic_item(
                    "p_fem_total",
                    metrics["p_fem_total"],
                    "Baixa participacao total de femeas afasta base reprodutiva no perfil de terminacao.",
                ),
                _deterministic_item(
                    "p_garrotes_25_36",
                    metrics["p_garrotes_25_36"],
                    "Garrotes de 25-36 meses relevantes sustentam a regra de engorda pura.",
                ),
            ]
        )
    elif system == "RECRIA_ENGORDA":
        evidence.extend(
            [
                _deterministic_item(
                    "p_mac_13_24",
                    metrics["p_mac_13_24"],
                    "Machos de 13-24 meses mostram etapa de recria ativa.",
                ),
                _deterministic_item(
                    "p_bois",
                    metrics["p_bois"],
                    "Bois adultos mostram etapa de engorda ativa.",
                ),
                _deterministic_item(
                    "intensidade_engorda",
                    metrics["intensidade_engorda"],
                    "Intensidade de engorda acompanha a leitura de recria-engorda quando ha informacao de venda.",
                ),
            ]
        )
    elif system == "CICLO_COMPLETO":
        evidence.extend(
            [
                _deterministic_item(
                    "p_matrizes",
                    metrics["p_matrizes"],
                    "Participacao de matrizes alimenta o score do ciclo completo.",
                ),
                _deterministic_item(
                    "p_mac_13_24",
                    metrics["p_mac_13_24"],
                    "Machos de 13-24 meses alimentam o score do ciclo completo.",
                ),
                _deterministic_item(
                    "p_bois",
                    metrics["p_bois"],
                    "Bois adultos alimentam o score do ciclo completo.",
                ),
                _deterministic_item(
                    "p_bez",
                    metrics["p_bez"],
                    "Bezerros de 0-24 meses alimentam o score do ciclo completo.",
                ),
                _deterministic_item(
                    "indice_ciclo",
                    metrics["indice_ciclo"],
                    f"Score de ciclo completo em {metrics['indice_ciclo']}/4 pelos sinais atuais.",
                ),
            ]
        )
    else:
        evidence.extend(
            [
                _deterministic_item(
                    "p_mac_13_24",
                    metrics["p_mac_13_24"],
                    "Machos de 13-24 meses sustentam o perfil de recria.",
                ),
                _deterministic_item(
                    "p_matrizes",
                    metrics["p_matrizes"],
                    "Participacao de matrizes abaixo do perfil de cria mantem a leitura em recria.",
                ),
                _deterministic_item(
                    "mature_matrix_ratio",
                    metrics["mature_matrix_ratio"],
                    "Razao de matrizes maduras ajuda a separar recria de um sistema de cria consolidado.",
                ),
            ]
        )

    return {
        "system": system,
        "deterministic_evidence": evidence,
        "ml_evidence": _ml_evidence(ml_result),
        "mixed_cycle": mixed_cycle_evidence(system, indicators, ml_result),
        "missing_data": list((ml_result or {}).get("dados_faltantes") or []),
    }
