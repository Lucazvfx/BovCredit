from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


_DEFAULT_MONTH_WEIGHTS = (1.0 / 12.0,) * 12


def _coerce_month_index(key: Any) -> int | None:
    try:
        month = int(key)
    except (TypeError, ValueError):
        return None
    return month if 1 <= month <= 12 else None


def _normalize_weights(weights: list[float]) -> list[float]:
    total = sum(weights)
    if total <= 0:
        return list(_DEFAULT_MONTH_WEIGHTS)
    return [value / total for value in weights]


def _coerce_month_weights(spec: Any) -> tuple[list[float], bool, list[str]]:
    warnings: list[str] = []
    if spec is None:
        return list(_DEFAULT_MONTH_WEIGHTS), True, warnings

    if isinstance(spec, Mapping):
        if "weights" in spec and len(spec) == 1:
            return _coerce_month_weights(spec["weights"])

        weights = [0.0] * 12
        seen = False
        for key, value in spec.items():
            month = _coerce_month_index(key)
            if month is None:
                continue
            seen = True
            try:
                weights[month - 1] = float(value)
            except (TypeError, ValueError):
                warnings.append(f"invalid weight for month {month}")
        if not seen:
            return list(_DEFAULT_MONTH_WEIGHTS), True, ["seasonality mapping did not contain month weights"]
        return _normalize_weights(weights), False, warnings

    if isinstance(spec, Sequence) and not isinstance(spec, (str, bytes, bytearray)):
        values = list(spec)
        if len(values) != 12:
            raise ValueError("seasonality sequences must contain exactly 12 monthly weights")
        weights = []
        for value in values:
            try:
                weights.append(float(value))
            except (TypeError, ValueError):
                warnings.append("seasonality contained a non-numeric weight")
                weights.append(0.0)
        return _normalize_weights(weights), False, warnings

    raise ValueError("seasonality must be a 12-month sequence or a mapping of month weights")


def resolve_month_weights(
    category: str,
    calendar: dict | None = None,
    seasonality: dict | None = None,
) -> tuple[list[float], bool, list[str]]:
    calendar = calendar or {}
    seasonality = seasonality or {}

    cal_spec = calendar.get(category)
    sea_spec = seasonality.get(category)

    if cal_spec is None and sea_spec is None:
        return list(_DEFAULT_MONTH_WEIGHTS), True, [
            f"no seasonality provided for {category}; using linear monthly fallback",
        ]

    cal_weights = None
    cal_estimated = False
    cal_warnings: list[str] = []
    if cal_spec is not None:
        cal_weights, cal_estimated, cal_warnings = _coerce_month_weights(cal_spec)

    sea_weights = None
    sea_estimated = False
    sea_warnings: list[str] = []
    if sea_spec is not None:
        sea_weights, sea_estimated, sea_warnings = _coerce_month_weights(sea_spec)

    warnings = cal_warnings + sea_warnings

    if cal_weights is None:
        weights = sea_weights or list(_DEFAULT_MONTH_WEIGHTS)
        return weights, sea_estimated, warnings
    if sea_weights is None:
        return cal_weights, cal_estimated, warnings

    combined = [a * b for a, b in zip(cal_weights, sea_weights)]
    return _normalize_weights(combined), cal_estimated or sea_estimated, warnings


def distribute_amount(amount: float, month_weights: list[float]) -> list[float]:
    amount = float(amount or 0.0)
    if len(month_weights) != 12:
        raise ValueError("month_weights must contain 12 entries")
    rounded: list[float] = []
    accumulated = 0.0
    for index, weight in enumerate(month_weights):
        if index == 11:
            value = round(amount - accumulated, 2)
        else:
            value = round(amount * weight, 2)
            accumulated += value
        rounded.append(value)
    return rounded
