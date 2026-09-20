"""Pipeline ponta a ponta para análise de crédito de culturas anuais e grãos.

Encadeia:
    PlanoSafra → Produção e Economia (COE/COT/Breakeven) → Projeção Plurianual
    → Capacidade de Pagamento (DSCR / SAC / Price) → Fluxo Mensal → Testes de Estresse
    → Parecer e Dicas
"""
from __future__ import annotations

from typing import Any, Mapping

from services.fluxo_mensal_credito import projetar_fluxo_mensal
from services.payment_capacity_engine import calculate_payment_capacity
from services.stress_engine import run_stress_tests

from .dicas import gerar_dicas_graos
from .economics import calcular_economico_safra
from .models import CulturaSafra, PlanoSafra, SAFRA_VERAO, SAFRA_SAFRINHA
from .projector import projetar_safras_anuais


def cenarios_graos_padrao() -> list[dict[str, Any]]:
    """Cenários de estresse típicos para grãos e culturas anuais."""
    return [
        {'nome': 'quebra_safra_20pct', 'revenue_pct': -20},
        {'nome': 'queda_preco_graos_15pct', 'price_pct': -15},
        {'nome': 'alta_custo_insumos_15pct', 'cost_pct': 15},
        {'nome': 'atraso_escoamento_comercializacao', 'commercialization_delay_months': 3},
        {'nome': 'choque_combinado_clima_preco', 'revenue_pct': -15, 'price_pct': -10, 'cost_pct': 10},
    ]


def _float(v: Any, padrao: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return padrao


def _int(v: Any, padrao: int = 0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return padrao


def montar_plano_safra(payload: Mapping[str, Any]) -> PlanoSafra:
    """Constrói o objeto PlanoSafra a partir de um dicionário JSON."""
    culturas_raw = payload.get('culturas') or []
    culturas_list = []

    for c in culturas_raw:
        culturas_list.append(
            CulturaSafra(
                cultura=str(c.get('cultura') or '').strip().upper(),
                safra_tipo=str(c.get('safra_tipo') or SAFRA_VERAO).strip().upper(),
                area_ha=_float(c.get('area_ha')),
                produtividade_ha=_float(c.get('produtividade_ha')),
                preco_unitario=_float(c.get('preco_unitario')),
                coe_ha=_float(c.get('coe_ha')),
                cot_ha=_float(c.get('cot_ha')) if c.get('cot_ha') is not None else None,
                unidade=str(c.get('unidade') or 'sc').strip().lower(),
                identificacao=str(c.get('identificacao') or '').strip(),
            )
        )

    return PlanoSafra(
        culturas=tuple(culturas_list),
        ano_agricola=str(payload.get('ano_agricola') or '2026/27').strip(),
        ano_base=_int(payload.get('ano_base'), 2026),
        despesas_administrativas=_float(payload.get('despesas_administrativas'), 0.0),
    )


def analisar_culturas_anuais(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Executa a análise agronômica, econômica e de crédito para lavouras de grãos."""
    payload = payload or {}
    plano = montar_plano_safra(payload)

    # 1. Análise Econômica da Safra
    economico = calcular_economico_safra(plano)

    # 2. Projeção Plurianual (dimensionada pelo prazo do financiamento)
    credito_pedido = dict(payload.get('credito') or {})
    prazo_meses = _int(credito_pedido.get('prazo_meses'), 12)
    anos_projecao = max(-(-prazo_meses // 12), 1) if prazo_meses > 0 else 5
    if anos_projecao < 3 and credito_pedido.get('valor', 0) > 0:
        # Se for financiamento, projeta ao menos 3 anos para avaliar consistência
        anos_projecao = max(anos_projecao, 3)

    projecao_resultado = projetar_safras_anuais(plano, anos=anos_projecao)
    linhas_anos = projecao_resultado['anos']

    # 3. Capacidade de Pagamento e Crédito
    credito_normalizado = {
        'credito_valor': _float(credito_pedido.get('credito_valor') or credito_pedido.get('valor')),
        'prazo_meses': _int(credito_pedido.get('prazo_meses'), 12),
        'carencia_meses': _int(credito_pedido.get('carencia_meses'), 0),
        'juros_aa': _float(credito_pedido.get('juros_aa'), 0.115),
        'sistema_amortizacao': str(credito_pedido.get('sistema_amortizacao') or credito_pedido.get('sistema') or 'sac').lower(),
        'periodicidade_meses': _int(credito_pedido.get('periodicidade_meses'), 12),
    }

    cashflow = {
        'geracao_caixa_anual': economico['resultado_operacional'],
        'projecao_anos': [
            {
                'ano': linha['ano'],
                'ano_calendario': linha['ano_calendario'],
                'receita': linha['receita'],
                'custo': linha['custo'],
                'resultado': linha['resultado'],
            }
            for linha in linhas_anos
        ],
    }

    divida_existente = {
        'parcela_existente_mensal': _float(payload.get('parcela_existente_mensal'), 0.0),
    }

    credito = calculate_payment_capacity(cashflow, credito_normalizado, divida_existente)
    analise_cred = credito.get('analysis') or {}

    # 4. Fluxo Mensal
    fluxo_mensal = projetar_fluxo_mensal(cashflow['projecao_anos'])

    # 5. Testes de Estresse
    servico_por_ano = {
        _int(periodo.get('ano')): periodo.get('servico_divida_anual', 0.0)
        for periodo in (credito.get('periods') or [])
    }
    linhas_stress = [
        dict(linha, servico_divida_anual=servico_por_ano.get(linha['ano'], 0.0))
        for linha in cashflow['projecao_anos']
    ]

    stress = run_stress_tests(
        {
            'projecao_anos': linhas_stress,
            'conclusao': analise_cred.get('conclusao', {}),
            'servico_divida_anual': analise_cred.get('servico_divida_media_anual', 0.0),
            'geracao_caixa_anual': analise_cred.get('geracao_caixa_anual', 0.0),
        },
        payload.get('stress_scenarios') or cenarios_graos_padrao(),
    )

    # 6. Dicas e Alertas
    dicas = gerar_dicas_graos(economico, credito, stress)

    return {
        'valido': True,
        'tipo': 'CULTURAS_ANUAIS_GRAOS',
        'ano_agricola': plano.ano_agricola,
        'ano_base': plano.ano_base,
        'area_fisica_ha': economico['area_fisica_ha'],
        'area_plantada_total_ha': economico['area_plantada_total_ha'],
        'economico': economico,
        'projecao': projecao_resultado,
        'credito': credito,
        'fluxo_mensal': fluxo_mensal,
        'stress': stress,
        'dicas': dicas,
        'avisos': economico.get('avisos') or [],
    }
