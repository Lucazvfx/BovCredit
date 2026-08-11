from __future__ import annotations

from typing import Any

from .risk_explanation import build_explanation


_COMPONENTS = (
    "payment_capacity",
    "resilience",
    "productive_efficiency",
    "herd_structure",
    "data_quality",
    "sensitivity",
    "projected_liquidity",
)


def _as_number(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bounded(score: float | None) -> int:
    if score is None:
        return 0
    return int(max(0, min(100, round(score))))


def _component_from_section(section: dict | None, *, kind: str) -> tuple[int, str]:
    section = dict(section or {})
    numeric = _as_number(section.get("score"))
    if numeric is not None:
        return _bounded(numeric), "score"

    if kind == "payment_capacity":
        for key in ("dscr", "capacidade", "coverage"):
            numeric = _as_number(section.get(key))
            if numeric is not None:
                return _bounded(min(100.0, numeric * 60.0)), key
    elif kind == "resilience":
        for key in ("stress_dscr", "dscr_estresse", "stress_ratio"):
            numeric = _as_number(section.get(key))
            if numeric is not None:
                return _bounded(min(100.0, numeric * 60.0)), key
        for key in ("stress_drop_pct", "queda_pct", "loss_pct"):
            numeric = _as_number(section.get(key))
            if numeric is not None:
                return _bounded(max(0.0, 100.0 - numeric)), key
    elif kind == "productive_efficiency":
        for key in ("efficiency_pct", "desempenho_pct", "desfrute_pct", "yield_pct"):
            numeric = _as_number(section.get(key))
            if numeric is not None:
                return _bounded(numeric), key
    elif kind == "herd_structure":
        for key in ("structure_pct", "balance_pct", "composition_pct", "matrix_score"):
            numeric = _as_number(section.get(key))
            if numeric is not None:
                return _bounded(numeric), key
    elif kind == "data_quality":
        for key in ("confidence_score", "data_confidence_score"):
            numeric = _as_number(section.get(key))
            if numeric is not None:
                return _bounded(numeric), key
    elif kind == "sensitivity":
        for key in ("sensitivity_score", "score_sensitivity", "robustness_pct"):
            numeric = _as_number(section.get(key))
            if numeric is not None:
                return _bounded(numeric), key
        for key in ("downside_pct", "risk_drop_pct"):
            numeric = _as_number(section.get(key))
            if numeric is not None:
                return _bounded(max(0.0, 100.0 - numeric)), key
    elif kind == "projected_liquidity":
        for key in ("liquidity_score", "projected_liquidity_score"):
            numeric = _as_number(section.get(key))
            if numeric is not None:
                return _bounded(numeric), key
        for key in ("liquidity_months", "months_positive_cash", "cashflow_months"):
            numeric = _as_number(section.get(key))
            if numeric is not None:
                return _bounded(min(100.0, numeric * 20.0)), key

    return 0, "missing"


def calculate_experimental_score(analysis: dict | None) -> dict:
    analysis = dict(analysis or {})
    components: dict[str, dict[str, Any]] = {}
    reasons: list[str] = []
    positive_factors: list[str] = []
    points_of_attention: list[str] = []
    assumptions: list[str] = [
        "Missing components count as zero in the experimental blend.",
    ]

    for component in _COMPONENTS:
        score, source_key = _component_from_section(analysis.get(component), kind=component)
        components[component] = {
            "score": score,
            "source": source_key,
            "weight": 1.0,
        }
        if score >= 60:
            positive_factors.append(f"{component} strong ({score}/100)")
            reasons.append(f"{component} contributes positively to the experimental score.")
        elif score > 0:
            points_of_attention.append(f"{component} needs attention ({score}/100)")
        else:
            points_of_attention.append(f"{component} missing or unscorable")

    score_1000 = int(round(sum(item["score"] for item in components.values()) / len(_COMPONENTS) * 10))
    score_1000 = max(0, min(1000, score_1000))

    if score_1000 >= 700:
        reasons.append("Signals are favorable, but the score remains experimental.")
    elif score_1000 >= 400:
        reasons.append("Signals are mixed and need more validation.")
    else:
        reasons.append("Signals are still weak for decision use.")

    if not positive_factors:
        positive_factors.append("No component cleared the strong threshold.")

    if not points_of_attention:
        points_of_attention.append("No extra attention points were identified.")

    result = {
        "score": score_1000,
        "experimental_score": score_1000,
        "scale": 1000,
        "components": components,
        "weights": {name: 1.0 for name in _COMPONENTS},
        "reasons": reasons,
        "positive_factors": positive_factors,
        "points_of_attention": points_of_attention,
        "assumptions": assumptions,
        "provenance": {
            "analysis_keys": sorted(analysis),
            "component_sources": {name: data["source"] for name, data in components.items()},
        },
        "limitations": [
            "Experimental and not validated for autonomous credit decisions.",
            "Weights are heuristic and must be calibrated with real cases.",
        ],
        "status": "EXPERIMENTAL",
        "experimental": True,
        "validated": False,
        "autonomous_credit_decision": False,
    }
    result.update(build_explanation(result))
    return result
