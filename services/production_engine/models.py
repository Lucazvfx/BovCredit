from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from services.engine.contracts import HerdState


@dataclass(frozen=True, slots=True)
class ProductionRequest:
    state: HerdState
    system: str
    parameters: Mapping[str, Any]
    years: int


@dataclass(frozen=True, slots=True)
class ProductionProjection:
    ciclo: str
    anos: tuple[dict[str, Any], ...]
    acumulado: MappingProxyType
    delta_rebanho: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "ciclo": self.ciclo,
            "anos": [dict(ano) for ano in self.anos],
            "acumulado": dict(self.acumulado),
            "delta_rebanho": self.delta_rebanho,
        }
