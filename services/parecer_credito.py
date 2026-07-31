"""Parecer de crédito: capacidade de pagamento (Price + DSCR) e montagem.

Módulo puro — não importa Flask nem DB. Recebe números já computados.
"""
from __future__ import annotations

# Faixas de política de crédito (DSCR) — ajustáveis, não são benchmark zootécnico.
DSCR_APROVAR = 1.30
DSCR_RESSALVA = 1.00


def parcela_price(pv: float, juros_aa: float, n_meses: int) -> float:
    """Parcela mensal por amortização Price. juros_aa nominal anual."""
    if n_meses <= 0 or pv <= 0:
        return 0.0
    i = (1 + juros_aa) ** (1 / 12) - 1
    if i <= 0:
        return pv / n_meses
    return pv * i / (1 - (1 + i) ** (-n_meses))


def credito_maximo(
    geracao_caixa_anual: float,
    juros_aa: float,
    prazo_meses: int,
    carencia_meses: int = 0,
    dividas_mensais: float = 0.0,
    dscr_alvo: float = DSCR_APROVAR,
) -> float:
    """
    Capacidade máxima de endividamento: PV tal que DSCR = dscr_alvo.

    Inverso do Price: parcela_max = caixa_disponivel / 12
    PV_max = parcela_max × (1 − (1+i)^−n) / i
    """
    n = max(prazo_meses - carencia_meses, 0)
    if n <= 0 or juros_aa <= 0 or geracao_caixa_anual <= 0:
        return 0.0
    caixa_disponivel = geracao_caixa_anual / dscr_alvo - 12 * max(dividas_mensais, 0.0)
    if caixa_disponivel <= 0:
        return 0.0
    parcela_max = caixa_disponivel / 12
    i = (1 + juros_aa) ** (1 / 12) - 1
    if i <= 0:
        return round(parcela_max * n, 2)
    return round(parcela_max * (1 - (1 + i) ** (-n)) / i, 2)


def avaliar_capacidade_pagamento(
    geracao_caixa_anual: float,
    credito_valor: float,
    prazo_meses: int,
    juros_aa: float,
    carencia_meses: int = 0,
    dividas_mensais: float = 0.0,
) -> dict:
    n = max(prazo_meses - carencia_meses, 0)
    parcela = parcela_price(credito_valor, juros_aa, n)
    servico_anual = 12 * (parcela + max(dividas_mensais, 0.0))
    cap_max = credito_maximo(geracao_caixa_anual, juros_aa, prazo_meses,
                             carencia_meses, dividas_mensais)

    if servico_anual <= 0:
        return {'dscr': None, 'parcela_mensal': round(parcela, 2),
                'servico_divida_anual': 0.0,
                'geracao_caixa_anual': round(geracao_caixa_anual, 2),
                'capacidade_maxima': cap_max,
                'recomendacao': None, 'faixa': None,
                'justificativa': 'Sem crédito a avaliar.'}

    dscr = geracao_caixa_anual / servico_anual
    if geracao_caixa_anual <= 0:
        rec, just = 'negar', 'Operação não gera caixa positivo — sem capacidade de pagamento.'
    elif dscr >= DSCR_APROVAR:
        rec, just = 'aprovar', f'Cobertura {dscr:.2f} — folga confortável sobre o serviço da dívida.'
    elif dscr >= DSCR_RESSALVA:
        rec, just = 'ressalva', f'Cobertura {dscr:.2f} — operação cobre a dívida com folga estreita.'
    else:
        rec, just = 'negar', f'Cobertura {dscr:.2f} — geração de caixa insuficiente para o serviço da dívida.'

    return {'dscr': round(dscr, 2), 'parcela_mensal': round(parcela, 2),
            'servico_divida_anual': round(servico_anual, 2),
            'geracao_caixa_anual': round(geracao_caixa_anual, 2),
            'capacidade_maxima': cap_max,
            'recomendacao': rec, 'faixa': rec, 'justificativa': just}


def _fmt_rs(v) -> str:
    return f'R$ {v:,.0f}'.replace(',', '.')


def avaliar_capacidade_no_prazo(conclusao_ano1: dict, projecao_anos: list,
                                prazo_meses: int) -> dict:
    """
    Reavalia a capacidade de pagamento sobre TODOS os anos do financiamento.

    O DSCR do ano 1 sozinho engana: numa pecuária o primeiro ano liquida o
    estoque acumulado no rebanho declarado (bois prontos, machos em idade de
    abate), enquanto os anos seguintes vendem apenas a produção corrente. Um
    ciclo completo chegou a projetar DSCR 6,08 no ano 1 e −0,53 no ano 2 —
    e o parecer aprovava, embora a dívida seja paga ao longo de 36 meses.

    Devolve a conclusão revisada com `memoria`: a lista de passos que levaram
    à recomendação, para o analista conferir o raciocínio em vez de receber
    só o veredicto.

    Args:
        conclusao_ano1: saída de avaliar_capacidade_pagamento().
        projecao_anos: lista por ano com 'ano', 'dscr', 'resultado', 'viavel'.
        prazo_meses: prazo do crédito, que define quantos anos avaliar.
    """
    base = dict(conclusao_ano1)
    if not projecao_anos or not base.get('dscr'):
        return base

    n_anos = max(1, min(-(-prazo_meses // 12), len(projecao_anos)))  # teto
    avaliados = projecao_anos[:n_anos]
    dscrs = [(a['ano'], a['dscr']) for a in avaliados if a.get('dscr') is not None]
    if not dscrs:
        return base

    ano_pior, dscr_min = min(dscrs, key=lambda t: t[1])
    dscr_medio = sum(d for _, d in dscrs) / len(dscrs)
    n_viaveis = sum(1 for a in avaliados if a.get('viavel'))

    memoria = [{
        'passo':   'Prazo do crédito',
        'valor':   f'{prazo_meses} meses',
        'detalhe': f'A capacidade de pagamento é avaliada sobre {n_anos} '
                   f'ano(s) de projeção, não apenas o primeiro.',
    }, {
        'passo':   'Serviço da dívida',
        'valor':   f'{_fmt_rs(base["servico_divida_anual"])}/ano',
        'detalhe': f'Parcela de {_fmt_rs(base["parcela_mensal"])} × 12, '
                   f'somada a dívidas já existentes.',
    }]
    for ano, d in dscrs:
        res = next((a.get('resultado') for a in avaliados if a['ano'] == ano), None)
        nota = ('liquida o estoque de animais prontos declarado na ficha'
                if ano == 1 else 'vende apenas a produção corrente do rebanho')
        memoria.append({
            'passo':   f'DSCR do ano {ano}',
            'valor':   f'{d:.2f}',
            'detalhe': (f'Geração de caixa de {_fmt_rs(res)} — {nota}.'
                        if res is not None else nota),
        })

    # A recomendação segue o ANO MAIS FRACO do prazo: é nele que a operação
    # deixa de cobrir a dívida, e a dívida vence de todo jeito.
    if dscr_min >= DSCR_APROVAR:
        rec = 'aprovar'
        just = (f'Cobertura mínima {dscr_min:.2f} no ano {ano_pior} — a operação '
                f'sustenta o serviço da dívida em todos os {n_anos} anos do prazo.')
    elif dscr_min >= DSCR_RESSALVA:
        rec = 'ressalva'
        just = (f'Cobertura cai para {dscr_min:.2f} no ano {ano_pior}. A operação '
                f'ainda cobre a dívida, mas sem folga em todo o prazo.')
    else:
        rec = 'negar'
        just = (f'Cobertura cai para {dscr_min:.2f} no ano {ano_pior}, abaixo de '
                f'1,00 — a operação deixa de cobrir a dívida antes do fim do prazo.')

    rebaixado = rec != base['recomendacao']
    memoria.append({
        'passo':   'Ano crítico',
        'valor':   f'ano {ano_pior} · DSCR {dscr_min:.2f}',
        'detalhe': 'É o ano mais fraco do prazo, e é ele que define a '
                   'recomendação — a dívida vence independentemente.',
    })
    memoria.append({
        'passo':   'Anos viáveis',
        'valor':   f'{n_viaveis} de {n_anos}',
        'detalhe': 'Ano viável = gera caixa positivo e cobre o serviço da dívida.',
    })
    if rebaixado:
        memoria.append({
            'passo':   'Rebaixamento',
            'valor':   f'{base["recomendacao"].upper()} → {rec.upper()}',
            'detalhe': f'O ano 1 isolado indicava {base["recomendacao"]} '
                       f'(DSCR {base["dscr"]:.2f}), mas ele liquida o estoque '
                       f'acumulado e não se repete.',
        })

    base.update({
        'recomendacao':      rec,
        'faixa':             rec,
        'justificativa':     just,
        'dscr_ano1':         base['dscr'],
        'dscr_minimo':       round(dscr_min, 2),
        'dscr_medio':        round(dscr_medio, 2),
        'ano_critico':       ano_pior,
        'anos_avaliados':    n_anos,
        'anos_viaveis':      n_viaveis,
        'rebaixado_no_prazo': rebaixado,
        'memoria':           memoria,
    })
    return base


def montar_parecer(*, identificacao, composicao, indicadores, benchmarks,
                   consistencia, financeiro, geracao_caixa_anual, credito,
                   fluxo_gep=None, sensibilidade=None, shap_explicacao=None,
                   projecao_anos=None, garantia=None, endividamento=None) -> dict:
    def _f(v, default=0.0):
        try: return float(v or default)
        except (TypeError, ValueError): return default
    def _i(v, default=0):
        try: return int(float(v or default))
        except (TypeError, ValueError): return default

    conclusao = avaliar_capacidade_pagamento(
        geracao_caixa_anual=geracao_caixa_anual,
        credito_valor=_f(credito.get('credito_valor')),
        prazo_meses=_i(credito.get('prazo_meses')),
        juros_aa=_f(credito.get('juros_aa')),
        carencia_meses=_i(credito.get('carencia_meses')),
        dividas_mensais=_f(credito.get('dividas_mensais')))

    # Reavalia sobre todos os anos do prazo — o DSCR do ano 1 isolado engana.
    conclusao = avaliar_capacidade_no_prazo(
        conclusao, projecao_anos or [], _i(credito.get('prazo_meses')))

    # ── Rebaixamentos ───────────────────────────────────────────────────────
    # Capacidade de pagamento, garantia, endividamento e consistência são
    # perguntas independentes: o fluxo pode cobrir a parcela e mesmo assim o
    # rebanho não cobrir o principal numa execução. Vale a pior das respostas.
    #
    # Cada motivo é registrado na memória mesmo quando a recomendação já caiu
    # por outro — o comitê precisa ver TODOS os problemas, não só o primeiro
    # que disparou. Só a transição da recomendação é condicional.
    _g = garantia or {}
    _e = endividamento or {}
    erros = (consistencia or {}).get('resumo', {}).get('erros', 0)

    _motivos = []
    if _g.get('veredito') == 'insuficiente':
        _motivos.append((
            f'garantia insuficiente (LTV {_g.get("ltv")}% sobre o valor de execução)',
            {'passo':   'Rebaixamento por garantia',
             'valor':   f'LTV {_g.get("ltv")}%',
             'detalhe': 'A capacidade de pagamento cobre a parcela, mas o rebanho '
                        'deságiado não cobre o principal numa execução. As duas '
                        'perguntas são independentes e vale a pior.'}))
    if _e.get('alerta') == 'critico':
        _motivos.append((
            f'endividamento total compromete {_e.get("comprometimento_pct")}% '
            f'da geração de caixa',
            {'passo':   'Rebaixamento por endividamento',
             'valor':   f'{_e.get("comprometimento_pct")}%',
             'detalhe': 'Somado o serviço das dívidas já existentes, a operação '
                        'passa a consumir mais caixa do que a política admite.'}))
    if erros:
        _motivos.append((
            f'{erros} erro(s) de consistência no rebanho declarado invalidam a projeção',
            {'passo':   'Rebaixamento por consistência',
             'valor':   f'{erros} erro(s)',
             'detalhe': 'Divergências no rebanho declarado invalidam a base da '
                        'projeção, então a recomendação cai para ressalva.'}))

    if _motivos:
        if conclusao['recomendacao'] == 'aprovar':
            conclusao = dict(
                conclusao, recomendacao='ressalva',
                justificativa=conclusao['justificativa'] + ' Rebaixado: '
                + '; '.join(m[0] for m in _motivos) + '.')
        conclusao.setdefault('memoria', []).extend(m[1] for m in _motivos)

    return {
        'secoes': ['identificacao', 'composicao', 'indicadores',
                   'consistencia', 'financeiro', 'fluxo_gep', 'garantia',
                   'endividamento', 'sensibilidade', 'shap_explicacao',
                   'conclusao'],
        'identificacao': identificacao,
        'composicao': composicao,
        'indicadores': {'valores': indicadores, 'benchmarks': benchmarks},
        'consistencia': consistencia,
        'financeiro': financeiro,
        'fluxo_gep': fluxo_gep,
        'garantia': garantia,
        'endividamento': endividamento,
        'sensibilidade': sensibilidade,
        'shap_explicacao': shap_explicacao or {},
        'conclusao': conclusao,
    }
