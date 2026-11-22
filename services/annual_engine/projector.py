"""Projeção plurianual de culturas anuais para dimensionamento de crédito.

Para custeio agrícola de safra única, o horizonte é de 1 ano.
Para investimentos plurianuais (tratores, colheitadeiras, armazéns, correção de solo),
a capacidade de pagamento precisa ser testada ao longo de todo o prazo do contrato
(ex: 3 a 10 anos).
"""
from __future__ import annotations

from typing import Any, Mapping

from .economics import calcular_economico_safra
from .models import PlanoSafra


def projetar_safras_anuais(
    plano: PlanoSafra,
    anos: int = 5,
    modificadores_anuais: Sequence[Mapping[str, float]] | None = None,
) -> dict[str, Any]:
    """Gera a projeção plurianual do plano de safra para análise de crédito.

    Cada ano projeta a receita e custos do plano de safra, com suporte opcional
    a modificadores de preço/produtividade por ano.
    """
    if anos <= 0:
        raise ValueError('anos deve ser maior que zero')

    base_economica = calcular_economico_safra(plano)

    linhas = []
    for i in range(anos):
        ano_indice = i + 1
        ano_calendario = plano.ano_base + i

        # Se houver modificadores por ano (ex: choques ou tendências)
        mod = (modificadores_anuais[i] if modificadores_anuais and i < len(modificadores_anuais) else {})
        fator_preco = float(mod.get('fator_preco', 1.0))
        fator_custo = float(mod.get('fator_custo', 1.0))
        fator_prod = float(mod.get('fator_produtividade', 1.0))

        receita_ano = round(base_economica['receita_total'] * fator_preco * fator_prod, 2)
        custo_ano = round(base_economica['cot_total'] * fator_custo, 2)
        resultado_ano = round(receita_ano - custo_ano, 2)

        linhas.append({
            'ano': ano_indice,
            'ano_calendario': ano_calendario,
            'ano_safra': f'{ano_calendario}/{str(ano_calendario + 1)[-2:]}',
            'receita': receita_ano,
            'custo': custo_ano,
            'resultado': resultado_ano,
            'coe': round(base_economica['coe_total'] * fator_custo, 2),
            'area_plantada_ha': base_economica['area_plantada_total_ha'],
        })

    return {
        'ano_base': plano.ano_base,
        'anos': linhas,
        'acumulado': {
            'receita': round(sum(l['receita'] for l in linhas), 2),
            'custo': round(sum(l['custo'] for l in linhas), 2),
            'resultado': round(sum(l['resultado'] for l in linhas), 2),
        },
        'base_economica': base_economica,
    }
