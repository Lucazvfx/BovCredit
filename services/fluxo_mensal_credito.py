"""Projeção mensal de caixa para análise de crédito.

Quando a ficha não traz calendário de vendas e despesas, a distribuição mensal
é uma aproximação linear. Ela é explicitamente marcada como estimada.
"""
from __future__ import annotations


def projetar_fluxo_mensal(anos: list[dict]) -> dict:
    meses = []
    saldo = 0.0
    for ano in anos or []:
        receita = float(ano.get('receita', 0) or 0) / 12.0
        custo = float(ano.get('custo', 0) or 0) / 12.0
        servico = float(ano.get('servico_divida_anual', 0) or 0) / 12.0
        for mes in range(1, 13):
            entrada = receita
            saidas = custo + servico
            fluxo_livre = entrada - saidas
            saldo += fluxo_livre
            meses.append({
                'ano': int(ano.get('ano', 1)),
                'mes': mes,
                'receita_estimada': round(entrada, 2),
                'custo_operacional_estimado': round(custo, 2),
                'servico_divida': round(servico, 2),
                'fluxo_livre': round(fluxo_livre, 2),
                'saldo_acumulado': round(saldo, 2),
            })
    min_mes = min(meses, key=lambda x: x['saldo_acumulado']) if meses else None
    return {
        'metodo': 'distribuicao_linear_anual_estimada',
        'meses': meses,
        'saldo_minimo': min_mes['saldo_acumulado'] if min_mes else 0.0,
        'mes_critico': ({'ano': min_mes['ano'], 'mes': min_mes['mes']}
                        if min_mes else None),
        'aviso': 'Sem calendário mensal informado, receitas e custos foram distribuídos linearmente. Use dados mensais reais para decisão final.',
    }

