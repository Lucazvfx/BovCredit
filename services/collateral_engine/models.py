"""Modelos de dados para a Matriz de Garantias e Cálculo de LTV no agronegócio B2B.

Regras de precificação, deságio de liquidação forçada e cobertura de risco para comitês de crédito.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class TipoGarantia(str, Enum):
    IMOVEL_RURAL = "IMOVEL_RURAL"            # Hipoteca ou Alienação Fiduciária de Terra
    PENHOR_SAFRA = "PENHOR_SAFRA"            # Penhor Agrícola de Grãos / CPR
    PENHOR_REBANHO = "PENHOR_REBANHO"        # Penhor Pecuário de Bovinos
    AVAL_PESSOAL = "AVAL_PESSOAL"            # Fiança / Aval de Pessoa Física ou Jurídica
    SEGURO_AGRICOLA = "SEGURO_AGRICOLA"      # Apólice endossada ao credor


class TipoGravame(str, Enum):
    ALIENACAO_FIDUCIARIA = "ALIENACAO_FIDUCIARIA"  # Preferência máxima; rito extrajudicial (Lei 9.514/97)
    HIPOTECA_1_GRAU = "HIPOTECA_1_GRAU"            # Hipoteca de primeiro grau com preferência
    HIPOTECA_2_GRAU = "HIPOTECA_2_GRAU"            # Hipoteca de segundo grau (apenas saldo remanescente)
    PENHOR_PRIMEIRO_GRAU = "PENHOR_PRIMEIRO_GRAU"  # Penhor cedular sobre a lavoura ou rebanho
    AVAL_SOLIDARIO = "AVAL_SOLIDARIO"              # Devedor solidário


class ClassificacaoGarantia(str, Enum):
    EXCELENTE = "EXCELENTE"        # LTV <= 55% | ICG >= 180%
    ADEQUADA = "ADEQUADA"          # 55% < LTV <= 75% | 133% <= ICG < 180%
    AJUSTADA = "AJUSTADA"          # 75% < LTV <= 90% | 111% <= ICG < 133%
    INSUFICIENTE = "INSUFICIENTE"  # LTV > 90% | ICG < 111%


# Deságios de liquidação forçada padrão de mercado B2B
DESAGIOS_PADRAO_GARANTIA: dict[TipoGravame, float] = {
    TipoGravame.ALIENACAO_FIDUCIARIA: 0.20,      # Terra em Alienação: 20% de deságio (leilão rápido)
    TipoGravame.HIPOTECA_1_GRAU: 0.30,           # Terra em Hipoteca 1º Grau: 30% (execução judicial)
    TipoGravame.HIPOTECA_2_GRAU: 0.45,           # Terra em Hipoteca 2º Grau: 45% (risco subordinado)
    TipoGravame.PENHOR_PRIMEIRO_GRAU: 0.25,      # Penhor de Safra/CPR: 25% (risco climático/armazenagem)
    TipoGravame.AVAL_SOLIDARIO: 0.50,            # Aval pessoal: 50% (deságio de liquidez de bens)
}


@dataclass
class ItemGarantia:
    id_garantia: str
    tipo: TipoGarantia
    gravame: TipoGravame
    descricao: str
    identificador_registro: str  # ex: "Matrícula 12.345 - CRI Rondonópolis" ou "CPR 2026/01"
    area_ha: float = 0.0
    valor_mercado_bruto: float = 0.0
    dividas_previas_averbadas: float = 0.0
    desagio_aplicado_pct: float = 0.0
    valor_liquidacao_forcada: float = 0.0
    observacoes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["tipo"] = self.tipo.value
        d["gravame"] = self.gravame.value
        return d


@dataclass
class MatrizGarantiasConsolidada:
    itens: list[ItemGarantia]
    credito_solicitado: float
    valor_mercado_total: float
    valor_liquidacao_total: float
    ltv_pct: float                 # (Crédito / Valor Liquidação) * 100
    indice_cobertura_pct: float    # (Valor Liquidação / Crédito) * 100
    sobra_ou_deficit_garantia: float
    classificacao_risco: ClassificacaoGarantia
    suficiente_para_aprovacao: bool
    recomendacao_comite: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "itens": [i.to_dict() for i in self.itens],
            "credito_solicitado": round(self.credito_solicitado, 2),
            "valor_mercado_total": round(self.valor_mercado_total, 2),
            "valor_liquidacao_total": round(self.valor_liquidacao_total, 2),
            "ltv_pct": round(self.ltv_pct, 2),
            "indice_cobertura_pct": round(self.indice_cobertura_pct, 2),
            "sobra_ou_deficit_garantia": round(self.sobra_ou_deficit_garantia, 2),
            "classificacao_risco": self.classificacao_risco.value,
            "suficiente_para_aprovacao": self.suficiente_para_aprovacao,
            "recomendacao_comite": self.recomendacao_comite,
        }
