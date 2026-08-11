from __future__ import annotations

from copy import deepcopy


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return [value]


def build_explanation(analysis: dict | None) -> dict:
    analysis = dict(analysis or {})
    explanation = {
        "status": analysis.get("status"),
        "confidence_score": analysis.get("confidence_score", analysis.get("data_confidence_score")),
        "data_confidence_score": analysis.get("data_confidence_score", analysis.get("confidence_score")),
        "reasons": _as_list(analysis.get("reasons")),
        "positive_factors": _as_list(analysis.get("positive_factors")),
        "points_of_attention": _as_list(analysis.get("points_of_attention")),
        "assumptions": _as_list(analysis.get("assumptions")),
        "provenance": deepcopy(analysis.get("provenance") or {}),
        "limitations": _as_list(analysis.get("limitations")),
    }
    for key in ("experimental", "validated", "autonomous_credit_decision", "score", "scale"):
        if key in analysis:
            explanation[key] = analysis[key]
    return explanation
