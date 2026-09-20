"""Módulo de Culturas Anuais e Grãos (Soja, Milho Safrinha, Algodão...)."""
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
    'PlanoSafra',
    'SAFRA_IRRIGADO',
    'SAFRA_SAFRINHA',
    'SAFRA_VERAO',
    'analisar_culturas_anuais',
    'calcular_economico_safra',
    'cenarios_graos_padrao',
    'detalhar_cultura',
    'gerar_dicas_graos',
    'montar_plano_safra',
    'projetar_safras_anuais',
]
