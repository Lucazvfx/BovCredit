"""Análise ponta a ponta da lavoura perene: produção → crédito.

Nenhuma fórmula nova. Esta camada só encadeia o que já existe:

    project_perennial_production   produção por ano (fase 1)
    resultado_economico            receita, custo e resultado (fase 2)
    calculate_payment_capacity     DSCR, cronograma, crédito máximo
    projetar_fluxo_mensal          mensalização
    run_stress_tests               cenários

O motor de crédito já reavalia todos os anos do prazo. Na perene isso deixa
de ser refinamento e vira o centro da análise: o ano apertado é o de carga
baixa do café ou o de reforma do canavial, e nenhum dos dois é o ano 1.
"""
from __future__ import annotations

from typing import Any, Mapping

from services.fluxo_mensal_credito import projetar_fluxo_mensal
from services.payment_capacity_engine import calculate_payment_capacity
from services.stress_engine import run_stress_tests

from .dicas import gerar_dicas
from .economics import resultado_economico
from .models import CurvaProdutividade, PerennialState, Talhao
from .projector import project_perennial_production


def cenarios_perene_padrao() -> list[dict]:
    """Os choques que a lavoura sofre — não os do rebanho.

    Os cenários padrão do motor de stress falam de natalidade, mortalidade e
    GMD. A matemática por trás é multiplicador de receita e de custo, e serve
    para qualquer atividade; os rótulos não. Um parecer de cafezal que lista
    "mortalidade_alta" perde credibilidade na primeira leitura.
    """
    return [
        {'nome': 'quebra_safra', 'revenue_pct': -20},
        {'nome': 'queda_preco', 'price_pct': -15},
        {'nome': 'custo_alto', 'cost_pct': 15},
        {'nome': 'atraso_comercializacao', 'commercialization_delay_months': 3},
        {'nome': 'choque_combinado', 'revenue_pct': -15, 'price_pct': -10,
         'cost_pct': 10},
    ]


def _int(valor, padrao=0) -> int:
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return padrao


def _float(valor, padrao=0.0) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return padrao


def montar_curvas(bruto: Mapping[str, Any] | None) -> dict[str, CurvaProdutividade]:
    """Constrói as curvas do payload.

    As chaves de `fatores` chegam como string quando vêm de JSON; idade é
    número. Sem esta conversão toda idade daria fator zero — a lavoura
    inteira apareceria em formação, e o parecer recusaria uma operação boa.
    """
    curvas: dict[str, CurvaProdutividade] = {}
    for cultura, dados in (bruto or {}).items():
        dados = dados or {}
        fatores = {
            _int(idade): _float(fator)
            for idade, fator in (dados.get('fatores') or {}).items()
        }
        curvas[str(cultura).strip().upper()] = CurvaProdutividade(
            cultura=str(cultura).strip().upper(),
            produtividade_plena=_float(dados.get('produtividade_plena')),
            unidade=str(dados.get('unidade') or '').strip() or 'unidade',
            fatores=fatores,
            ciclo_anos=_int(dados['ciclo_anos']) if dados.get('ciclo_anos') else None,
            bienalidade=_float(dados.get('bienalidade')),
            fonte=str(dados.get('fonte') or ''),
        )
    return curvas


def montar_estado(payload: Mapping[str, Any]) -> PerennialState:
    talhoes = tuple(
        Talhao(
            cultura=str(t.get('cultura') or '').strip().upper(),
            area_ha=_float(t.get('area_ha')),
            ano_plantio=_int(t.get('ano_plantio')),
            identificacao=str(t.get('identificacao') or '').strip(),
            fase_bienal=(t.get('fase_bienal') or None),
        )
        for t in (payload.get('talhoes') or [])
    )
    return PerennialState(talhoes=talhoes, ano_base=_int(payload.get('ano_base')))


def analisar_lavoura_perene(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Roda a análise completa e devolve os blocos do parecer agrícola."""
    payload = payload or {}
    anos = _int(payload.get('anos'), 6) or 6

    estado = montar_estado(payload)
    curvas = montar_curvas(payload.get('curvas'))
    producao = project_perennial_production(estado, curvas, years=anos)
    economico = resultado_economico(
        producao, payload.get('precos'), payload.get('custos'))

    linhas = economico['anos']
    projecao_anos = [
        {
            'ano': linha['ano'],
            'ano_calendario': linha['ano_calendario'],
            'receita': linha['receita'],
            'custo': linha['custo'],
            'resultado': linha['resultado'],
        }
        for linha in linhas
    ]

    credito_pedido = dict(payload.get('credito') or {})
    cashflow = {
        'geracao_caixa_anual': projecao_anos[0]['resultado'] if projecao_anos else 0.0,
        'projecao_anos': projecao_anos,
    }
    divida_existente = {
        'parcela_existente_mensal': _float(payload.get('parcela_existente_mensal')),
    }
    credito = calculate_payment_capacity(cashflow, credito_pedido, divida_existente)

    fluxo_mensal = projetar_fluxo_mensal(projecao_anos)

    analise = credito.get('analysis') or {}
    # O cenário precisa do serviço da dívida DE CADA ANO, não de um valor médio:
    # com carência, o ano 1 não paga nada e os seguintes pagam parcelas
    # diferentes no SAC. Passando só o agregado, o motor caía no serviço do
    # ano 1 — zero durante a carência — e devolvia DSCR nulo em todo cenário.
    servico_por_ano = {
        _int(periodo.get('ano')): periodo.get('servico_divida_anual', 0.0)
        for periodo in (credito.get('periods') or [])
    }
    linhas_stress = [
        dict(linha, servico_divida_anual=servico_por_ano.get(linha['ano'], 0.0))
        for linha in projecao_anos
    ]
    stress = run_stress_tests(
        {
            'projecao_anos': linhas_stress,
            'conclusao': analise.get('conclusao', {}),
            'servico_divida_anual': analise.get('servico_divida_media_anual', 0.0),
            'geracao_caixa_anual': analise.get('geracao_caixa_anual', 0.0),
        },
        payload.get('stress_scenarios') or cenarios_perene_padrao(),
    )

    avisos = list(economico['avisos'])
    pior = (credito.get('analysis') or {}).get('pior_periodo') or {}
    if pior.get('ano') and _int(pior.get('ano')) > 1:
        avisos.append(
            f'O ano mais apertado do contrato é o {_int(pior["ano"])}, não o '
            'primeiro. Avaliar a operação pelo ano 1 aprovaria crédito que '
            'não se paga no ano crítico.')

    resultado = {
        'valido': bool(economico['valido']),
        # As curvas voltam com a análise para o parecer poder citar a fonte de
        # cada uma — ou dizer que não há, o que muda o peso do documento.
        'curvas': {
            nome: {
                'produtividade_plena': curva.produtividade_plena,
                'unidade': curva.unidade,
                'bienalidade': curva.bienalidade,
                'ciclo_anos': curva.ciclo_anos,
                'fonte': curva.fonte,
            }
            for nome, curva in curvas.items()
        },
        'producao': producao,
        'economico': economico,
        'credito': credito,
        'fluxo_mensal': fluxo_mensal,
        'stress': stress,
        'projecao_anos': projecao_anos,
        'avisos': avisos,
    }
    resultado['dicas'] = gerar_dicas(resultado, credito_pedido)
    return resultado
