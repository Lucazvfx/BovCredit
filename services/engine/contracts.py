from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable


_ALLOWED_SOURCES = frozenset({"MANUAL", "PDF", "EXCEL", "API"})


def _freeze_value(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_value(inner) for key, inner in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze_value(item) for item in value)
    return value


def _as_frozen_mapping(value: dict | None, *, field_name: str) -> MappingProxyType:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a dict")
    return _freeze_value(value)


def _as_frozen_documents(values: list[dict] | None) -> tuple[MappingProxyType, ...]:
    if values is None:
        values = []
    if not isinstance(values, list):
        raise ValueError("source_documents must be a list")
    return tuple(_as_frozen_mapping(item, field_name="source_documents item") for item in values)


def _normalize_values(values: Iterable[Any]) -> tuple[float, ...]:
    normalized: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("values must be numeric")
        numeric = float(value)
        if numeric < 0:
            raise ValueError("values must be non-negative")
        normalized.append(numeric)
    if len(normalized) != 10:
        raise ValueError("values must contain exactly ten numeric values")
    return tuple(normalized)


@dataclass(frozen=True, slots=True)
class HerdState:
    values: tuple[float, ...]
    source: str
    farm_id: int | None
    metadata: MappingProxyType

    def __init__(
        self,
        values: list[float],
        source: str,
        farm_id: int | None,
        metadata: dict,
    ) -> None:
        if source not in _ALLOWED_SOURCES:
            raise ValueError(f"source must be one of {sorted(_ALLOWED_SOURCES)}")
        object.__setattr__(self, "values", _normalize_values(values))
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "farm_id", farm_id)
        object.__setattr__(self, "metadata", _as_frozen_mapping(metadata, field_name="metadata"))


@dataclass(frozen=True, slots=True)
class AnalysisContext:
    organization_id: int | None
    user_id: int | None
    input_data: MappingProxyType
    source_documents: tuple[MappingProxyType, ...]

    def __init__(
        self,
        organization_id: int | None,
        user_id: int | None,
        input_data: dict,
        source_documents: list[dict],
    ) -> None:
        object.__setattr__(self, "organization_id", organization_id)
        object.__setattr__(self, "user_id", user_id)
        object.__setattr__(self, "input_data", _as_frozen_mapping(input_data, field_name="input_data"))
        object.__setattr__(self, "source_documents", _as_frozen_documents(source_documents))


@dataclass(frozen=True, slots=True)
class EngineVersion:
    rules: str
    parameters: str
    model: str
