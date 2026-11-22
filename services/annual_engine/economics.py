"""Cálculos econômicos para culturas anuais e grãos: receita, COE/COT e breakeven.

Adota os conceitos padrão da agropecuária brasileira (Conab / IMEA):
- COE: Custo Operacional Efetivo (desembolso direto de safra: insumos, operações, frete)
- COT: Custo Operacional Total (COE + depreciações + pró-labore)
- Ponto de Equilíbrio (Breakeven):
    sc/ha de breakeven = COE/ha ÷ Preço da saca
    R$/sc de breakeven = COE/ha ÷ Produtividade esperada
"""
from __future__ import annotations

from typing import Any

from services.economic_engine.margins import calculate_economic_result
from .models import CulturaSafra, PlanoSafra


def detalhar_cultura(c: CulturaSafra) -> dict[str, Any]:
    """Retorna o detalhamento técnico e econômico de uma cultura no ano-safra."""
    receita_ha = round(c.produtividade_ha * c.preco_unitario, 2)
    margem_contrib_ha = round(receita_ha - c.coe_ha, 2)
    resultado_op_ha = round(receita_ha - c.cot_efetivo_ha, 2)
    margem_contrib_pct = round((margem_contrib_ha / receita_ha * 100), 1) if receita_ha > 0 else 0.0

    return {
        'cultura': c.cultura,
        'safra_tipo': c.safra_tipo,
        'identificacao': c.identificacao or f'{c.cultura} ({c.safra_tipo})',
        'area_ha': c.area_ha,
        'unidade': c.unidade,
        'produtividade_ha': c.produtividade_ha,
        'producao_total': c.producao_total,
        'preco_unitario': c.preco_unitario,
        'receita_bruta': c.receita_bruta,
        'receita_ha': receita_ha,
        'coe_ha': c.coe_ha,
        'coe_total': c.coe_total,
        'cot_ha': c.cot_efetivo_ha,
        'cot_total': c.cot_total,
        'margem_contribuicao_total': c.margem_contribuicao_total,
        'margem_contribuicao_ha': margem_contrib_ha,
        'margem_contribuicao_pct': margem_contrib_pct,
        'resultado_operacional_total': c.resultado_operacional_total,
        'resultado_operacional_ha': resultado_op_ha,
        'breakeven_sc_ha': c.breakeven_produtividade,
        'breakeven_preco': c.breakeven_preco,
        'margem_seguranca_sc_ha': c.margem_seguranca_sc_ha,
    }


def calcular_economico_safra(plano: PlanoSafra) -> dict[str, Any]:
    """Calcula o resultado consolidado e detalhado por cultura do PlanoSafra."""
    detalhes = [detalhar_cultura(c) for c in plano.culturas]

    receita_total = plano.receita_total
    coe_total = plano.coe_total
    cot_total = plano.cot_total
    resultado_op = plano.resultado_operacional

    area_fisica = plano.area_fisica_estimada_ha
    area_plantada = plano.area_plantada_total_ha

    # Métricas consolidadas por hectare
    receita_ha_plantado = round(receita_total / area_plantada, 2) if area_plantada > 0 else 0.0
    coe_ha_plantado = round(coe_total / area_plantada, 2) if area_plantada > 0 else 0.0
    cot_ha_plantado = round(cot_total / area_plantada, 2) if area_plantada > 0 else 0.0
    resultado_ha_plantado = round(resultado_op / area_plantada, 2) if area_plantada > 0 else 0.0

    resultado_ha_fisico = round(resultado_op / area_fisica, 2) if area_fisica > 0 else 0.0

    # Encadeia com o motor econômico padrão do BovCredit
    revenues_dict = {'receita_total': receita_total}
    costs_dict = {
        'custo_operacional': cot_total,
        'custo_manutencao': coe_total,
        'custo_reposicao': 0.0,
    }
    economic_result = calculate_economic_result(revenues_dict, costs_dict)

    avisos: list[str] = []
    for d in detalhes:
        if d['margem_seguranca_sc_ha'] < 0:
            avisos.append(
                f"A cultura {d['identificacao']} opera em prejuízo operacional já na estimativa básica: "
                f"breakeven de {d['breakeven_sc_ha']} {d['unidade']}/ha supera a produtividade de {d['produtividade_ha']} {d['unidade']}/ha."
            )
        elif d['breakeven_sc_ha'] >= (d['produtividade_ha'] * 0.85):
            avisos.append(
                f"A cultura {d['identificacao']} possui margem de segurança estreita: breakeven de "
                f"{d['breakeven_sc_ha']} {d['unidade']}/ha consome {round(d['breakeven_sc_ha']/d['produtividade_ha']*100, 1)}% da safra esperada."
            )

    return {
        'valido': True,
        'ano_agricola': plano.ano_agricola,
        'ano_base': plano.ano_base,
        'area_fisica_ha': area_fisica,
        'area_plantada_total_ha': area_plantada,
        'culturas': detalhes,
        'receita_total': receita_total,
        'coe_total': coe_total,
        'cot_total': cot_total,
        'despesas_administrativas': plano.despesas_administrativas,
        'margem_contribuicao_total': round(receita_total - coe_total, 2),
        'resultado_operacional': resultado_op,
        'metricas_ha': {
            'receita_ha_plantado': receita_ha_plantado,
            'coe_ha_plantado': coe_ha_plantado,
            'cot_ha_plantado': cot_ha_plantado,
            'resultado_ha_plantado': resultado_ha_plantado,
            'resultado_ha_fisico': resultado_ha_fisico,
        },
        'economic_result': economic_result,
        'avisos': avisos,
    }
