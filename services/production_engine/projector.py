from __future__ import annotations

from types import MappingProxyType
from typing import Any

from services.engine.contracts import HerdState

from .models import ProductionProjection, ProductionRequest

SYSTEM_ALIASES = {
    "CRIA_RECRIA": "CRIA",
    "RECRIA_ENGORDA": "ENGORDA",
}

_SUPPORTED_SYSTEMS = frozenset(
    {
        "CRIA",
        "RECRIA",
        "ENGORDA",
        "CICLO_COMPLETO",
    }
)


def _normalize_system(system: str) -> str:
    if not isinstance(system, str) or not system.strip():
        raise ValueError("system must be a non-empty string")
    normalized = system.strip().upper()
    return SYSTEM_ALIASES.get(normalized, normalized)


def _coerce_float(value: Any, *, default: float | None = None) -> float:
    if value is None:
        if default is None:
            raise ValueError("missing required numeric parameter")
        return float(default)
    if isinstance(value, bool):
        raise ValueError("numeric parameters must not be boolean")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("numeric parameters must be numeric") from exc


def _coerce_int(value: Any, *, default: int) -> int:
    if value is None:
        return int(default)
    if isinstance(value, bool):
        raise ValueError("integer parameters must not be boolean")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("integer parameters must be numeric") from exc


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    return bool(value)


def build_request(state: HerdState, system: str, parameters: dict, years: int = 5) -> ProductionRequest:
    if not isinstance(state, HerdState):
        raise TypeError("state must be a HerdState")
    normalized_system = _normalize_system(system)
    if normalized_system not in _SUPPORTED_SYSTEMS:
        raise ValueError(f"unsupported system '{system}'")
    if parameters is None:
        parameters = {}
    if not isinstance(parameters, dict):
        raise ValueError("parameters must be a dict")
    years_value = _coerce_int(years, default=5)
    if years_value <= 0:
        raise ValueError("years must be positive")
    return ProductionRequest(state=state, system=normalized_system, parameters=parameters, years=years_value)


def finalize_projection(ciclo: str, anos_proj: list[dict[str, Any]], total_ini: float, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    summary = ProductionProjection(
        ciclo=ciclo,
        anos=tuple(dict(ano) for ano in anos_proj),
        acumulado=MappingProxyType(
            {
                "receita": round(sum(float(ano["receita"]) for ano in anos_proj), 2),
                "custo": round(sum(float(ano["custo"]) for ano in anos_proj), 2),
                "resultado": round(sum(float(ano["resultado"]) for ano in anos_proj), 2),
            }
        ),
        delta_rebanho=int(round(float(anos_proj[-1]["total"]) - float(total_ini))),
    )
    result = summary.as_dict()
    if extra:
        result.update(extra)
    return result


def project_production(state: HerdState, system: str, parameters: dict, years: int = 5) -> dict[str, Any]:
    request = build_request(state, system, parameters, years)

    if request.system == "CRIA":
        from .cria import project_cria

        return project_cria(request.state, request.parameters, years=request.years)
    if request.system == "RECRIA":
        from .recria import project_recria

        return project_recria(request.state, request.parameters, years=request.years)
    if request.system == "ENGORDA":
        from .engorda import project_engorda

        return project_engorda(request.state, request.parameters, years=request.years)
    if request.system == "CICLO_COMPLETO":
        from .ciclo_completo import project_full_cycle

        return project_full_cycle(request.state, request.parameters, years=request.years)

    raise ValueError(f"unsupported system '{system}'")
