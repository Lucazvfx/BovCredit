"""Modelos de dados e tipos para o motor de Compliance Socioambiental & ESG (Bacen).

Conforme as diretrizes do Manual de Crédito Rural (MCR 2-1) e Resoluções CMN 4.945/21
e CMN 5.081/23.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class StatusCAR(str, Enum):
    ATIVO = "ATIVO"
    PENDENTE = "PENDENTE"
    SUSPENSO = "SUSPENSO"
    CANCELADO = "CANCELADO"


class Bioma(str, Enum):
    AMAZONIA_FLORESTA = "AMAZONIA_FLORESTA"      # 80% Reserva Legal
    AMAZONIA_CERRADO = "AMAZONIA_CERRADO"        # 35% Reserva Legal (Cerrado na Amazônia Legal)
    CERRADO = "CERRADO"                          # 20% Reserva Legal
    MATA_ATLANTICA = "MATA_ATLANTICA"            # 20% Reserva Legal
    CAATINGA = "CAATINGA"                        # 20% Reserva Legal
    PAMPA = "PAMPA"                              # 20% Reserva Legal
    PANTANAL = "PANTANAL"                        # 20% Reserva Legal


class ParecerESG(str, Enum):
    APROVADO = "APROVADO"
    ALERTA = "ALERTA"
    IMPEDIDO_BACEN = "IMPEDIDO_BACEN"


# Percentuais de Reserva Legal obrigatória por bioma (Lei 12.651/2012)
PERCENTUAIS_RESERVA_LEGAL: dict[Bioma, float] = {
    Bioma.AMAZONIA_FLORESTA: 0.80,
    Bioma.AMAZONIA_CERRADO: 0.35,
    Bioma.CERRADO: 0.20,
    Bioma.MATA_ATLANTICA: 0.20,
    Bioma.CAATINGA: 0.20,
    Bioma.PAMPA: 0.20,
    Bioma.PANTANAL: 0.20,
}


@dataclass
class ResultadoCAR:
    numero_car: str
    status: StatusCAR
    bioma: Bioma
    area_total_ha: float
    area_reserva_legal_ha: float
    area_app_ha: float
    percentual_rl_declarado: float
    percentual_rl_exigido: float
    deficit_ou_excedente_rl_ha: float
    em_conformidade_florestal: bool
    sintaxe_valida: bool
    observacoes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["bioma"] = self.bioma.value
        return d


@dataclass
class ResultadoChecagensPublicas:
    embargo_ibama: bool
    embargo_icmbio: bool
    trabalho_escravo_mte: bool
    sobreposicao_terra_indigena: bool
    sobreposicao_unidade_conservacao: bool
    detalhes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DossieSocioambiental:
    parecer: ParecerESG
    score_esg: int  # 0 a 100
    selo_conformidade_cmn: str
    elegivel_credito_rural: bool
    car: ResultadoCAR
    checagens: ResultadoChecagensPublicas
    motivos_impedimento: list[str] = field(default_factory=list)
    alertas_monitoramento: list[str] = field(default_factory=list)
    recomendacoes_comite: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "parecer": self.parecer.value,
            "score_esg": self.score_esg,
            "selo_conformidade_cmn": self.selo_conformidade_cmn,
            "elegivel_credito_rural": self.elegivel_credito_rural,
            "car": self.car.to_dict(),
            "checagens": self.checagens.to_dict(),
            "motivos_impedimento": self.motivos_impedimento,
            "alertas_monitoramento": self.alertas_monitoramento,
            "recomendacoes_comite": self.recomendacoes_comite,
        }
