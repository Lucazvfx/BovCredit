from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class CashflowMonth:
    ano: int
    mes: int
    saldo_inicial: float
    entradas: float
    custos_operacionais: float
    investimentos: float
    parcelas: float
    juros: float
    saldo_operacional: float
    saldo_final: float
    estimated: bool
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CashflowProjection:
    months: tuple[CashflowMonth, ...]
    estimated: bool
    warnings: tuple[str, ...]
    saldo_minimo: float
    mes_critico: dict[str, int] | None
    method: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "months": [month.to_dict() for month in self.months],
            "estimated": self.estimated,
            "warnings": list(self.warnings),
            "saldo_minimo": self.saldo_minimo,
            "mes_critico": self.mes_critico,
            "method": self.method,
        }
