"""Módulo de Culturas Anuais e Grãos (Soja, Milho Safrinha, Algodão, Barter e CPR)."""
from .barter import (
    PRAÇAS_REFERENCIA,
    OperacaoBarter,
    calcular_barter,
    gerar_minuta_cpr,
)
from .dicas import gerar_dicas_graos
from .economics import calcular_economico_safra, detalhar_cultura
from .models import (
    CulturaSafra,
    PlanoSafra,
    SAFRA_IRRIGADO,
    SAFRA_SAFRINHA,
    SAFRA_VERAO,
)
from .pipeline import analisar_culturas_anuais, cenarios_graos_padrao, montar_plano_safra
from .projector import projetar_safras_anuais

__all__ = [
    'CulturaSafra',
    'OperacaoBarter',
    'PRAÇAS_REFERENCIA',
    'PlanoSafra',
    'SAFRA_IRRIGADO',
    'SAFRA_SAFRINHA',
    'SAFRA_VERAO',
    'analisar_culturas_anuais',
    'calcular_barter',
    'calcular_economico_safra',
    'cenarios_graos_padrao',
    'detalhar_cultura',
    'gerar_dicas_graos',
    'gerar_minuta_cpr',
    'montar_plano_safra',
    'projetar_safras_anuais',
]
