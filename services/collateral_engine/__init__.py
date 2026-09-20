"""Módulo de Matriz de Garantias, Deságios e LTV para operações B2B.
"""
from .calculator import calcular_item_garantia, consolidar_matriz_garantias
from .models import (
    DESAGIOS_PADRAO_GARANTIA,
    ClassificacaoGarantia,
    ItemGarantia,
    MatrizGarantiasConsolidada,
    TipoGarantia,
    TipoGravame,
)
from .pipeline import avaliar_matriz_garantias

__all__ = [
    "ClassificacaoGarantia",
    "ItemGarantia",
    "MatrizGarantiasConsolidada",
    "TipoGarantia",
    "TipoGravame",
    "DESAGIOS_PADRAO_GARANTIA",
    "avaliar_matriz_garantias",
    "calcular_item_garantia",
    "consolidar_matriz_garantias",
]
