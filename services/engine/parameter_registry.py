from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.proveniencia import declarado, e_parametro, referencia


@dataclass(frozen=True, slots=True)
class Parameter:
    name: str
    value: float
    unit: str
    system: str
    region: str | None
    source: str
    reference_year: int | None
    editable: bool
    plausible_range: tuple[float, float]


_REGISTRY: dict[tuple[str, str, str | None], Parameter] = {}


def _normalize_system(system: str) -> str:
    if not isinstance(system, str) or not system.strip():
        raise ValueError("system must be a non-empty string")
    return system.strip().upper()


def _normalize_region(region: str | None) -> str | None:
    if region is None:
        return None
    normalized = str(region).strip().upper()
    return normalized or None


def _registry_key(name: str, system: str, region: str | None = None) -> tuple[str, str, str | None]:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must be a non-empty string")
    return (name.strip(), _normalize_system(system), _normalize_region(region))


def register_parameter(
    name: str,
    value: float,
    *,
    unit: str,
    system: str,
    region: str | None = None,
    source: str | None = None,
    reference_year: int | None = None,
    editable: bool = True,
    plausible_range: tuple[float, float] | None = None,
) -> None:
    if source is None and e_parametro(value):
        source = value.fonte or ""
    if reference_year is None and e_parametro(value):
        reference_year = value.ano
    if plausible_range is None:
        numeric = float(value)
        plausible_range = (numeric, numeric)
    lo, hi = (float(plausible_range[0]), float(plausible_range[1]))
    if lo > hi:
        raise ValueError("plausible_range lower bound must be <= upper bound")

    parameter = Parameter(
        name=name.strip(),
        value=value,
        unit=unit,
        system=_normalize_system(system),
        region=_normalize_region(region),
        source=source or "",
        reference_year=reference_year,
        editable=bool(editable),
        plausible_range=(lo, hi),
    )
    _REGISTRY[_registry_key(name, system, region)] = parameter


def _ensure_registry_loaded() -> None:
    if _REGISTRY:
        return
    import services.parametros_zootecnicos  # noqa: F401


def _match_parameter(name: str, system: str, region: str | None = None) -> Parameter:
    _ensure_registry_loaded()
    normalized_name, normalized_system, normalized_region = _registry_key(name, system, region)
    for key in (
        (normalized_name, normalized_system, normalized_region),
        (normalized_name, normalized_system, None),
    ):
        parameter = _REGISTRY.get(key)
        if parameter is not None:
            return parameter
    raise KeyError(f"unknown parameter '{normalized_name}' for system '{normalized_system}'")


def _parameters_for_system(system: str, region: str | None = None) -> dict[str, Parameter]:
    _ensure_registry_loaded()
    normalized_system = _normalize_system(system)
    normalized_region = _normalize_region(region)
    matched: dict[str, Parameter] = {}
    for parameter in _REGISTRY.values():
        if parameter.system != normalized_system:
            continue
        if parameter.region not in (None, normalized_region):
            continue
        previous = matched.get(parameter.name)
        if previous is None or (previous.region is None and parameter.region == normalized_region):
            matched[parameter.name] = parameter
    return matched


def get_parameter(name: str, system: str, region: str | None = None) -> Parameter:
    return _match_parameter(name, system, region)


def _default_value(parameter: Parameter):
    if e_parametro(parameter.value):
        return parameter.value
    return referencia(
        float(parameter.value),
        parameter.source,
        ano=parameter.reference_year,
        rotulo=parameter.name,
    )


def _coerce_override(name: str, raw_value: Any) -> float:
    if isinstance(raw_value, bool):
        raise ValueError(f"override for '{name}' must be numeric")
    try:
        return float(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"override for '{name}' must be numeric") from exc


def resolve_parameters(overrides: dict, system: str, region: str | None = None) -> dict:
    if overrides is None:
        overrides = {}
    if not isinstance(overrides, dict):
        raise ValueError("overrides must be a dict")

    parameters = _parameters_for_system(system, region)
    resolved = {
        name: _default_value(parameter)
        for name, parameter in parameters.items()
    }

    for name, raw_value in overrides.items():
        parameter = parameters.get(name)
        if parameter is None:
            raise KeyError(f"unknown parameter '{name}' for system '{_normalize_system(system)}'")
        if not parameter.editable:
            raise ValueError(f"parameter '{name}' is not editable")
        numeric = _coerce_override(name, raw_value)
        lo, hi = parameter.plausible_range
        if numeric < lo or numeric > hi:
            raise ValueError(
                f"override for '{name}' must stay within plausible range {lo:.1f}..{hi:.1f}"
            )
        rotulo = parameter.value.rotulo if e_parametro(parameter.value) else parameter.name
        resolved[name] = declarado(
            numeric,
            fonte=f"Declarado pelo analista — default {parameter.source}",
            rotulo=rotulo,
        )

    return resolved


__all__ = [
    "Parameter",
    "get_parameter",
    "register_parameter",
    "resolve_parameters",
]
