"""Dicas e alertas técnicos/financeiros para análise de crédito de culturas anuais e grãos.

Orientações acionáveis para o comitê de crédito e analista rural:
- Breakeven alto em relação à média regional
- Margem de segurança estreita
- Descasamento de cronograma de pagamento com a colheita
- Cenários de estresse críticos (quebra de safra ou choque de preços)
"""
from __future__ import annotations

from typing import Any, Mapping

ATENCAO = 'atencao'
INFORMACAO = 'informacao'
SUCESSO = 'sucesso'


def _dica(tipo: str, titulo: str, texto: str) -> dict[str, str]:
    return {'tipo': tipo, 'titulo': titulo, 'texto': texto}


def gerar_dicas_graos(
    economico: Mapping[str, Any],
    credito: Mapping[str, Any] | None = None,
    stress: Mapping[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Analisa os dados de produção, custos e crédito e devolve dicas acionáveis."""
    dicas: list[dict[str, str]] = []
    culturas = economico.get('culturas') or []

    # 1. Alertas de Breakeven por Cultura
    for c in culturas:
        nome = c.get('identificacao') or c.get('cultura')
        unidade = c.get('unidade', 'sc')
        prod = float(c.get('produtividade_ha', 0))
        be = float(c.get('breakeven_sc_ha', 0))
        ms = float(c.get('margem_seguranca_sc_ha', 0))

        if ms < 0:
            dicas.append(_dica(
                ATENCAO,
                f'Operação deficitária em {nome}',
                f'O breakeven ({be:.1f} {unidade}/ha) supera a produtividade esperada ({prod:.1f} {unidade}/ha). '
                f'Mesmo sem quebra de clima, a receita não cobre os desembolsos diretos (COE).'
            ))
        elif prod > 0 and (be / prod) >= 0.80:
            dicas.append(_dica(
                ATENCAO,
                f'Margem de segurança estreita em {nome}',
                f'O breakeven consome {(be/prod*100):.1f}% da produtividade esperada ({be:.1f} de {prod:.1f} {unidade}/ha). '
                f'Uma quebra climática modesta de {(ms/prod*100):.1f}% já colocará a lavoura no vermelho.'
            ))
        elif prod > 0 and (be / prod) <= 0.55:
            dicas.append(_dica(
                SUCESSO,
                f'Excelente margem de segurança em {nome}',
                f'O custo operacional (COE) é pago com apenas {be:.1f} {unidade}/ha ({(be/prod*100):.1f}% da safra). '
                f'O produtor retém {ms:.1f} {unidade}/ha como margem livre.'
            ))

    # 2. Análise de Capacidade de Pagamento / DSCR
    if credito:
        analise_cred = credito.get('analysis') or {}
        dscr_min = float(analise_cred.get('dscr_minimo') or 0.0)
        dscr_medio = float(analise_cred.get('dscr_medio') or 0.0)

        if dscr_min > 0 and dscr_min < 1.0:
            dicas.append(_dica(
                ATENCAO,
                'DSCR abaixo de 1,0x — Risco de Inadimplência',
                f'No ano mais apertado o DSCR atinge {dscr_min:.2f}x. A geração de caixa livre da safra '
                f'não cobre a totalidade do serviço da dívida. Sugere-se alongamento de prazo ou readequação do valor.'
            ))
        elif dscr_min >= 1.30:
            dicas.append(_dica(
                SUCESSO,
                'Capacidade de pagamento confortável',
                f'DSCR mínimo de {dscr_min:.2f}x (médio de {dscr_medio:.2f}x). A safra gera folga sólida '
                f'para honrar as parcelas do financiamento.'
            ))

    # 3. Cenários de Estresse
    if stress:
        scenarios = stress.get('scenarios') or []
        descobertos = [s for s in scenarios if s.get('uncovered')]
        if descobertos:
            nomes = ', '.join(str(s.get('nome', '')).replace('_', ' ') for s in descobertos)
            dicas.append(_dica(
                ATENCAO,
                f'{len(descobertos)} cenário(s) de estresse rompem o caixa',
                f'Em {nomes} a geração de caixa fica abaixo do serviço da dívida. '
                f'Recomenda-se exigir seguro agrícola (multirrisco) ou travas de preços (hedge/barter).'
            ))

    return dicas
