from __future__ import annotations

from copy import deepcopy
from typing import Any

from .risk_explanation import build_explanation


_CORE_REQUIRED_FIELDS = {
    "preco_arroba",
    "custo_arroba",
    "peso_medio_kg",
    "taxa_natalidade_pct",
    "taxa_mortalidade_pct",
}

_OPTIONAL_TRACKED_FIELDS = {
    "preco_boi",
    "preco_vaca",
    "custo_manutencao",
    "custo_reposicao",
    "custo_operacional",
    "peso_desmama_kg",
    "taxa_prenhez_pct",
    "desmama_pct",
    "ganho_peso_kg_dia",
    "desfrute_pct",
    "receita_prevista",
    "fluxo_caixa_previsto",
    "liquidez_projetada",
}

_TRACKED_FIELDS = _CORE_REQUIRED_FIELDS | _OPTIONAL_TRACKED_FIELDS

_PRICE_GROUP = {"preco_arroba"}
_COST_GROUP = {"custo_arroba"}
_WEIGHT_GROUP = {"peso_medio_kg"}
_INDEX_GROUP = {"taxa_natalidade_pct", "taxa_mortalidade_pct"}
_HERD_GROUP = {"total_rebanho", "composicao_rebanho"}
_GROUPS = (
    ("prices", _PRICE_GROUP),
    ("costs", _COST_GROUP),
    ("weights", _WEIGHT_GROUP),
    ("indexes", _INDEX_GROUP),
    ("herd", _HERD_GROUP),
)

_SPECIAL_HERD_KEYS = {"values", "valores", "total", "total_animais", "total_rebanho"}
_PERCENT_FIELDS = {
    "taxa_natalidade_pct",
    "taxa_mortalidade_pct",
    "taxa_prenhez_pct",
    "desmama_pct",
    "desfrute_pct",
}


def _normalize_mapping(data: dict | None) -> dict[str, Any]:
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("expected mapping inputs")
    return dict(data)


def _coerce_number(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _field_status(field: str, numeric: float | None) -> str:
    if numeric is None:
        return "missing"
    if numeric < 0:
        return "impossible"
    if field in _PERCENT_FIELDS and numeric > 100:
        return "impossible"
    return "present"


def _group_present(fields: dict[str, dict[str, Any]], group_fields: set[str]) -> bool:
    for field in group_fields:
        status = fields.get(field, {}).get("status")
        if status in {"present", "assumed"}:
            return True
    return False


def _collect_sources(input_data: dict, herd: dict, production: dict) -> dict[str, list[tuple[str, Any]]]:
    index: dict[str, list[tuple[str, Any]]] = {}
    for source_name, source_data in (
        ("input_data", input_data),
        ("herd", herd),
        ("production", production),
    ):
        for key, value in source_data.items():
            if key in _SPECIAL_HERD_KEYS:
                continue
            index.setdefault(key, []).append((source_name, value))
    return index


def assess_data_quality(
    input_data: dict,
    herd: dict,
    production: dict | None = None,
) -> dict:
    input_data = _normalize_mapping(input_data)
    herd = _normalize_mapping(herd)
    production = _normalize_mapping(production)

    source_index = _collect_sources(input_data, herd, production)
    fields: dict[str, dict[str, Any]] = {}
    missing_fields: list[str] = []
    inconsistent_fields: list[str] = []
    impossible_fields: list[str] = []
    conflicting_fields: list[str] = []
    assumed_fields: list[dict[str, Any]] = []
    extra_fields: dict[str, list[dict[str, Any]]] = {}

    for source_name, source_data in (
        ("input_data", input_data),
        ("herd", herd),
        ("production", production),
    ):
        for key, value in source_data.items():
            if key not in _TRACKED_FIELDS and key not in _SPECIAL_HERD_KEYS:
                extra_fields.setdefault(key, []).append(
                    {"source": source_name, "value": deepcopy(value)}
                )

    for field in sorted(_TRACKED_FIELDS):
        occurrences = source_index.get(field, [])
        numeric_values: list[float] = []
        raw_values: list[tuple[str, Any]] = []
        for source_name, value in occurrences:
            raw_values.append((source_name, deepcopy(value)))
            numeric = _coerce_number(value)
            if numeric is None:
                if value not in (None, ""):
                    conflicting_fields.append(field)
                continue
            numeric_values.append(numeric)

        if not raw_values:
            if field in _CORE_REQUIRED_FIELDS:
                missing_fields.append(field)
            continue

        if len({round(value, 8) for value in numeric_values}) > 1:
            conflicting_fields.append(field)

        chosen_value = numeric_values[0] if numeric_values else None
        status = _field_status(field, chosen_value)
        if status == "impossible":
            impossible_fields.append(field)

        if field in _CORE_REQUIRED_FIELDS and status == "missing":
            missing_fields.append(field)

        fields[field] = {
            "value": chosen_value,
            "status": status if chosen_value is not None else "missing",
            "sources": [
                {"source": source_name, "value": deepcopy(value)}
                for source_name, value in raw_values
            ],
        }

    herd_values = herd.get("values") or herd.get("valores") or []
    herd_total = herd.get("total") or herd.get("total_animais") or herd.get("total_rebanho")
    herd_sum = None
    if isinstance(herd_values, (list, tuple)) and herd_values:
        numeric_values = [x for x in (_coerce_number(v) for v in herd_values) if x is not None]
        if numeric_values:
            herd_sum = sum(numeric_values)
            if herd_total in (None, ""):
                assumed_fields.append(
                    {
                        "campo": "total_rebanho",
                        "valor": herd_sum,
                        "origem": "herd.values",
                        "motivo": "derived from composition",
                    }
                )
                fields["total_rebanho"] = {
                    "value": herd_sum,
                    "status": "assumed",
                    "sources": [{"source": "herd.values", "value": list(herd_values)}],
                }
            else:
                herd_total_numeric = _coerce_number(herd_total)
                if herd_total_numeric is not None and abs(herd_total_numeric - herd_sum) > 0.5:
                    inconsistent_fields.append("total_rebanho")

    group_presence = {name: _group_present(fields, group_fields) for name, group_fields in _GROUPS}
    present_groups = sum(group_presence.values())
    present_fields = sum(1 for item in fields.values() if item["status"] in {"present", "assumed"})
    issue_count = (
        len(missing_fields)
        + len(inconsistent_fields)
        + len(impossible_fields)
        + len(conflicting_fields)
    )
    confidence_score = max(
        0,
        min(
            100,
            present_groups * 18
            + present_fields * 2
            - len(assumed_fields) * 4
            - issue_count * 3
            - (1 if extra_fields else 0),
        ),
    )

    if present_groups == len(_GROUPS) and issue_count == 0:
        status = "COMPLETO"
    elif present_groups >= 2:
        status = "PARCIAL"
    else:
        status = "INSUFICIENTE"

    reasons: list[str] = []
    positive_factors: list[str] = []
    points_of_attention: list[str] = []
    assumptions: list[str] = []

    reasons.append(f"{present_groups}/{len(_GROUPS)} essential groups available.")
    for group_name, group_fields in _GROUPS:
        if group_presence[group_name]:
            positive_factors.append(f"{group_name} available")
        else:
            points_of_attention.append(f"missing group: {group_name}")

    for field in missing_fields:
        points_of_attention.append(f"missing field: {field}")
    for field in inconsistent_fields:
        points_of_attention.append(f"inconsistent field: {field}")
    for field in impossible_fields:
        points_of_attention.append(f"impossible field: {field}")
    for field in conflicting_fields:
        points_of_attention.append(f"conflicting field: {field}")

    for assumed in assumed_fields:
        assumptions.append(
            f"{assumed['campo']} assumed from {assumed['origem']} ({assumed['motivo']})"
        )
        points_of_attention.append(f"assumed field: {assumed['campo']}")

    if extra_fields:
        points_of_attention.append(
            f"{len(extra_fields)} extra field(s) were preserved outside the core model"
        )

    limitations = [
        "Data quality measures completeness and consistency, not economic validation.",
        "Missing or assumed fields reduce confidence and require human review.",
    ]

    provenance = {
        "input_data": {
            "fields": sorted(k for k in input_data if k not in _SPECIAL_HERD_KEYS),
            "extra_fields": deepcopy(extra_fields),
        },
        "herd": {
            "has_values": bool(herd_values),
            "total_source": "assumed_from_values"
            if herd_total in (None, "") and herd_sum is not None
            else "declared",
        },
        "production": {
            "fields": sorted(production),
        },
    }

    result = {
        "status": status,
        "confidence_score": confidence_score,
        "data_confidence_score": confidence_score,
        "missing_fields": missing_fields,
        "inconsistent_fields": inconsistent_fields,
        "impossible_fields": impossible_fields,
        "conflicting_fields": conflicting_fields,
        "assumed_fields": assumed_fields,
        "fields": fields,
        "extra_fields": extra_fields,
        "group_presence": group_presence,
        "reasons": reasons,
        "positive_factors": positive_factors,
        "points_of_attention": points_of_attention,
        "assumptions": assumptions,
        "provenance": provenance,
        "limitations": limitations,
    }
    result.update(build_explanation(result))
    return result
