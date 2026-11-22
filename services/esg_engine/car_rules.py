"""Regras de validação de CAR (Cadastro Ambiental Rural) e Código Florestal.

Lei 12.651/2012 (Novo Código Florestal Brasileiro).
"""
from __future__ import annotations

import re
from typing import Any

from .models import (
    PERCENTUAIS_RESERVA_LEGAL,
    Bioma,
    ResultadoCAR,
    StatusCAR,
)

# Padrão Federal SICAR: UF-1234567-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA (UF + 7 dígitos + 32 alfanuméricos)
_PADRAO_SICAR = re.compile(r'^[A-Z]{2}-[0-9A-Z]{6,8}-[0-9A-F]{24,36}$', re.IGNORECASE)

_UFS_VALIDAS = {
    'AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA',
    'MT', 'MS', 'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN',
    'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO'
}


def validar_sintaxe_car(numero_car: str) -> tuple[bool, str]:
    """Valida se o número do CAR obedece ao padrão estrutural do SICAR / órgãos estaduais."""
    limpo = (numero_car or '').strip().upper()
    if not limpo:
        return False, 'Número do CAR não informado.'

    partes = limpo.split('-')
    if len(partes) < 3:
        return False, 'Formato inválido. O padrão SICAR requer UF-MUNICÍPIO-CÓDIGO (ex: MT-5107602-C75A...).'

    uf = partes[0]
    if uf not in _UFS_VALIDAS:
        return False, f'UF "{uf}" inválida no número do CAR.'

    if not _PADRAO_SICAR.match(limpo):
        # Tolera pequenas variações de sistemas estaduais se tiver pelo menos 20 caracteres e as 3 partes
        if len(limpo) >= 20 and all(p for p in partes):
            return True, 'Formato aceito (padrão estadual com código estendido).'
        return False, 'Código verificador do CAR fora do padrão nacional do SICAR.'

    return True, 'Formato SICAR válido.'


def calcular_metricas_florestais(
    numero_car: str,
    status: StatusCAR | str,
    bioma: Bioma | str,
    area_total_ha: float,
    area_reserva_legal_ha: float,
    area_app_ha: float = 0.0,
) -> ResultadoCAR:
    """Calcula e valida os parâmetros florestais da propriedade rural."""
    if isinstance(status, str):
        try:
            status = StatusCAR(status.upper())
        except ValueError:
            status = StatusCAR.PENDENTE

    if isinstance(bioma, str):
        try:
            bioma = Bioma(bioma.upper())
        except ValueError:
            bioma = Bioma.CERRADO

    area_tot = max(0.0, float(area_total_ha or 0.0))
    area_rl = max(0.0, float(area_reserva_legal_ha or 0.0))
    area_app = max(0.0, float(area_app_ha or 0.0))

    sintaxe_ok, motivo_sintaxe = validar_sintaxe_car(numero_car)

    perc_exigido = PERCENTUAIS_RESERVA_LEGAL.get(bioma, 0.20)
    area_rl_exigida = area_tot * perc_exigido

    perc_declarado = (area_rl / area_tot) if area_tot > 0 else 0.0
    deficit_ou_excedente = area_rl - area_rl_exigida

    # Tolerância de arredondamento de 0.5% ou regular se área declarada cobre a exigência
    em_conformidade = (deficit_ou_excedente >= -0.01) if area_tot > 0 else False

    obs: list[str] = [motivo_sintaxe]
    if not em_conformidade and area_tot > 0:
        obs.append(
            f'Déficit de Reserva Legal: {abs(deficit_ou_excedente):.1f} ha abaixo do exigido '
            f'para o bioma {bioma.value} ({perc_exigido * 100:.0f}%).'
        )
    elif area_tot > 0:
        obs.append(
            f'Reserva Legal em conformidade: {perc_declarado * 100:.1f}% declarado '
            f'vs {perc_exigido * 100:.0f}% exigido pelo Código Florestal.'
        )

    if status in (StatusCAR.SUSPENSO, StatusCAR.CANCELADO):
        obs.append(f'Atenção: CAR com status {status.value} impede a contratação de crédito rural.')
    elif status == StatusCAR.PENDENTE:
        obs.append('CAR pendente de homologação pelo órgão ambiental estadual competente.')

    return ResultadoCAR(
        numero_car=(numero_car or '').strip().upper(),
        status=status,
        bioma=bioma,
        area_total_ha=round(area_tot, 2),
        area_reserva_legal_ha=round(area_rl, 2),
        area_app_ha=round(area_app, 2),
        percentual_rl_declarado=round(perc_declarado, 4),
        percentual_rl_exigido=round(perc_exigido, 4),
        deficit_ou_excedente_rl_ha=round(deficit_ou_excedente, 2),
        em_conformidade_florestal=em_conformidade,
        sintaxe_valida=sintaxe_ok,
        observacoes=obs,
    )
