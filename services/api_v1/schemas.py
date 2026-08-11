from __future__ import annotations

from copy import deepcopy
from typing import Any

from flask import request

from .errors import MalformedRequestError, ValidationError


def load_json_body() -> dict:
    data = request.get_json(silent=True)
    if data is None:
        raise MalformedRequestError("Request body must be valid JSON.")
    if not isinstance(data, dict):
        raise MalformedRequestError("Request body must be a JSON object.")
    return data


def _coerce_number(value: Any, field: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or value is None:
        raise ValidationError(f"Field '{field}' must be numeric.")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Field '{field}' must be numeric.") from exc
    if minimum is not None and result < minimum:
        raise ValidationError(f"Field '{field}' must be >= {minimum}.")
    return result


def _coerce_int(value: Any, field: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or value is None:
        raise ValidationError(f"Field '{field}' must be an integer.")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Field '{field}' must be an integer.") from exc
    if minimum is not None and result < minimum:
        raise ValidationError(f"Field '{field}' must be >= {minimum}.")
    return result


def _require_dict(value: Any, field: str) -> dict:
    if value is None:
        raise ValidationError(f"Field '{field}' is required.")
    if not isinstance(value, dict):
        raise ValidationError(f"Field '{field}' must be an object.")
    return deepcopy(value)


def _values_from_payload(data: dict) -> list[float]:
    values = data.get("valores") or data.get("values")
    if not isinstance(values, list) or len(values) != 10:
        raise ValidationError("Field 'valores' must contain exactly 10 numbers.")
    coerced = []
    for index, value in enumerate(values):
        coerced.append(_coerce_number(value, f"valores[{index}]", minimum=0.0))
    if sum(coerced) < 10:
        raise ValidationError("Field 'valores' must have a total of at least 10.")
    return coerced


def parse_herd_payload(data: dict) -> dict:
    payload = deepcopy(data)
    payload["valores"] = _values_from_payload(payload)
    for field in ("bois_vendidos", "bezerros_vendidos"):
        if field in payload and payload[field] is not None:
            payload[field] = _coerce_number(payload[field], field, minimum=0.0)
    if "taxa_natalidade" in payload and payload["taxa_natalidade"] is not None:
        payload["taxa_natalidade"] = _coerce_number(payload["taxa_natalidade"], "taxa_natalidade", minimum=0.0)
    return payload


def parse_production_payload(data: dict) -> dict:
    payload = parse_herd_payload(data)
    system = (payload.get("system") or payload.get("ciclo") or "").strip().upper()
    if not system:
        raise ValidationError("Field 'system' is required.")
    years = _coerce_int(payload.get("years", payload.get("anos", 5)), "years", minimum=1)
    parameters = payload.get("parameters") or {}
    if not isinstance(parameters, dict):
        raise ValidationError("Field 'parameters' must be an object.")
    payload.update({
        "system": system,
        "years": years,
        "parameters": deepcopy(parameters),
    })
    return payload


def parse_cashflow_payload(data: dict) -> dict:
    payload = deepcopy(data)
    payload["annual_projection"] = _require_dict(
        payload.get("annual_projection") or payload.get("projecao_anos") or payload.get("analysis"),
        "annual_projection",
    )
    payload["debt_schedule"] = _require_dict(payload.get("debt_schedule"), "debt_schedule")
    payload["horizon_months"] = _coerce_int(payload.get("horizon_months", 12), "horizon_months", minimum=1)
    if payload.get("calendar") is not None and not isinstance(payload["calendar"], dict):
        raise ValidationError("Field 'calendar' must be an object.")
    if payload.get("seasonality") is not None and not isinstance(payload["seasonality"], dict):
        raise ValidationError("Field 'seasonality' must be an object.")
    return payload


def parse_payment_capacity_payload(data: dict) -> dict:
    payload = deepcopy(data)
    payload["cashflow"] = _require_dict(payload.get("cashflow"), "cashflow")
    payload["debt_request"] = _require_dict(payload.get("debt_request"), "debt_request")
    if payload.get("existing_debt") is not None:
        payload["existing_debt"] = _require_dict(payload.get("existing_debt"), "existing_debt")
    else:
        payload["existing_debt"] = {}
    return payload


def parse_stress_payload(data: dict) -> dict:
    payload = deepcopy(data)
    payload["base_analysis"] = _require_dict(payload.get("base_analysis"), "base_analysis")
    if payload.get("scenarios") is not None and not isinstance(payload["scenarios"], list):
        raise ValidationError("Field 'scenarios' must be an array.")
    return payload


def parse_full_analysis_payload(data: dict) -> dict:
    payload = deepcopy(data)
    if payload.get("valores") is None and payload.get("values") is None:
        raise ValidationError("Field 'valores' is required.")
    payload["valores"] = _values_from_payload(payload)
    return payload
