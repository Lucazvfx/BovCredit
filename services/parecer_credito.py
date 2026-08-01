"""Parecer de crédito: capacidade de pagamento (Price + DSCR) e montagem.

Módulo puro — não importa Flask nem DB. Recebe números já computados.
"""
from __future__ import annotations

import os

from services.proveniencia import politica, catalogo, resumo as _resumo_prov

# Faixas de política de crédito (DSCR) — ajustáveis, não são benchmark
# zootécnico. Marcadas como POLÍTICA na proveniência: em comitê elas se
# discutem, não se citam.
DSCR_APROVAR = politica(
    1.30, 'Política de crédito da instituição', rotulo='DSCR para aprovar',
    nota='Cobertura mínima do serviço da dívida no ano crítico do prazo.')
DSCR_RESSALVA = politica(
    1.00, 'Política de crédito da instituição', rotulo='DSCR para ressalva')


_CARENCIA_SEM_CAP = os.environ.get('CARENCIA_SEM_CAPITALIZACAO', '0') == '1'


def parcela_price(pv: float, juros_aa: float, n_meses: int) -> float:
    """Parcela mensal por amortização Price. juros_aa nominal anual."""
    if n_meses <= 0 or pv <= 0:
        return 0.0
    i = (1 + juros_aa) ** (1 / 12) - 1
    if i <= 0:
        return pv / n_meses
    return pv * i / (1 - (1 + i) ** (-n_meses))


def principal_apos_carencia(pv: float, juros_aa: float,
                            carencia_meses: int = 0) -> float:
    """Principal no fim da carência, com os juros do período incorporados.

    O sistema calculava a parcela sobre `prazo − carência` e mantinha o
    principal parado, como se a carência fosse de graça. Não é: durante ela o
    saldo devedor rende juros, e quem amortiza depois amortiza um saldo maior.

    Medido num crédito de R$ 1.000.000, 36 meses, 12 de carência a 12,5% a.a.:

        parcela antes ....... R$ 46.997
        parcela correta ..... R$ 52.871      a parcela precisa subir 12,5%

    A parcela saía 11,1% abaixo do devido e o DSCR subia na mesma proporção —
    ou seja, o erro corria a favor de APROVAR. E carência é padrão em custeio
    pecuário, então o caso não é raro.

    A OUTRA CONVENÇÃO, que existe e não é esta

    Há linhas em que o tomador PAGA os juros durante a carência, e só o
    principal fica suspenso. Nelas o saldo não cresce e a parcela de
    amortização é a de antes — mas há desembolso de juros nos meses da
    carência, que este modelo também não representava.

    Adotada a capitalização por ser a estrutura corrente em custeio e a mais
    conservadora das duas: superestimar a parcela erra contra aprovar, que é o
    lado seguro num produto de crédito. `CARENCIA_SEM_CAPITALIZACAO=1` volta ao
    comportamento anterior.
    """
    if pv <= 0 or carencia_meses <= 0 or juros_aa <= 0 or _CARENCIA_SEM_CAP:
        return max(pv, 0.0)
    i = (1 + juros_aa) ** (1 / 12) - 1
    return pv * (1 + i) ** carencia_meses


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
    pv_no_fim_da_carencia = parcela_max * (1 - (1 + i) ** (-n)) / i
    # Desconta a capitalização: o valor LIBERADO hoje é menor que o saldo que
    # será amortizado. Sem isto o crédito máximo ficaria acima do que a mesma
    # geração de caixa aguenta, e as duas funções — que são uma o inverso da
    # outra — passariam a discordar.
    fator = (1 + i) ** carencia_meses if (carencia_meses > 0 and not _CARENCIA_SEM_CAP) else 1.0
    return round(pv_no_fim_da_carencia / fator, 2)


def avaliar_capacidade_pagamento(
    geracao_caixa_anual: float,
    credito_valor: float,
    prazo_meses: int,
    juros_aa: float,
    carencia_meses: int = 0,
    dividas_mensais: float = 0.0,
) -> dict:
    n = max(prazo_meses - carencia_meses, 0)
    # O principal cresce durante a carência — ver principal_apos_carencia.
    _pv = principal_apos_carencia(credito_valor, juros_aa, carencia_meses)
    parcela = parcela_price(_pv, juros_aa, n)
    _cap_carencia = ({
        'carencia_meses':       carencia_meses,
        'principal_liberado':   round(credito_valor, 2),
        'principal_amortizado': round(_pv, 2),
        'acrescimo_pct':        round((_pv / credito_valor - 1) * 100, 1),
    } if _pv > credito_valor > 0 else None)
    servico_anual = 12 * (parcela + max(dividas_mensais, 0.0))
    cap_max = credito_maximo(geracao_caixa_anual, juros_aa, prazo_meses,
                             carencia_meses, dividas_mensais)

    if servico_anual <= 0:
        return {'dscr': None, 'parcela_mensal': round(parcela, 2),
                'capitalizacao_carencia': _cap_carencia,
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
            'capitalizacao_carencia': _cap_carencia,
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
    # A carência não é gratuita, e o parecer precisa dizer isso: o saldo rende
    # juros durante ela e a parcela seguinte amortiza um principal maior. Sem
    # esta linha, o analista vê uma parcela mais alta do que a conta ingênua
    # dele daria e não tem como saber de onde veio a diferença.
    _cap = base.get('capitalizacao_carencia')
    if _cap:
        memoria.append({
            'passo':   'Carência capitaliza juros',
            'valor':   f'{_fmt_rs(_cap["principal_liberado"])} → '
                       f'{_fmt_rs(_cap["principal_amortizado"])}',
            'detalhe': f'Durante os {_cap["carencia_meses"]} meses de carência o '
                       f'saldo rende juros e é incorporado ao principal '
                       f'(+{_cap["acrescimo_pct"]:.1f}%). A amortização recai '
                       f'sobre o saldo maior, então a parcela sobe na mesma '
                       f'proporção.',
        })
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


# Divergência do COE frente à referência da praça a partir da qual o parecer
# avisa. Limiar de política nosso, não norma: abaixo disso a diferença cabe em
# variação de sistema e de região; acima, o custo passa a ser candidato mais
# provável a causa da recusa do que a fazenda.
COE_DIVERGENCIA_AVISO = 25.0


def montar_parecer(*, identificacao, composicao, indicadores, benchmarks,
                   consistencia, financeiro, geracao_caixa_anual, credito,
                   fluxo_gep=None, sensibilidade=None, shap_explicacao=None,
                   projecao_anos=None, garantia=None, endividamento=None,
                   precos_regional=None) -> dict:
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

    # ── O custo que nega, mas não se apresenta ──────────────────────────────
    #
    # O sistema já comparava o COE calculado com a referência Campo Futuro/CNA
    # da praça e rotulava o nível — e depois negava o crédito sem nunca dizer
    # ao analista que o CUSTO podia ser o problema.
    #
    # Medido em rebanhos reais: a ficha de recria de 700 cabeças roda a
    # R$ 387,02/@ contra referência de R$ 183,50 (+110,9%); a cria de 1.705
    # roda +31,5%. Nos dois o parecer nega por caixa insuficiente, e a causa
    # provável do caixa insuficiente é o custo de entrada — que o analista
    # pode conferir e corrigir em trinta segundos, se souber que deve.
    #
    # Este aviso NÃO rebaixa nem altera número. Ele existe para que uma recusa
    # por custo fora da praça não seja lida como recusa por fazenda ruim. É a
    # diferença entre um parecer que nega e um parecer que se explica.
    _coe = (fluxo_gep or {}).get('coe_benchmark') or {}
    _delta = _coe.get('delta_pct')
    if _delta is not None and _delta >= COE_DIVERGENCIA_AVISO:
        # A referência é a FAIXA entre os painéis publicados da modalidade, não
        # um ponto: com dois painéis o delta mede quanto o custo passa do teto,
        # e uma fazenda entre eles não é apontada. Com um painel só, a faixa
        # degenera no ponto — e o texto precisa dizer isso, senão promete uma
        # dispersão que não existe.
        _faixa = _coe.get('faixa_paineis')
        _n     = _coe.get('n_paineis') or 1
        if _faixa and _n > 1:
            _lo, _hi = _faixa
            _contra = (f'a faixa de R$ {_lo:.2f}–{_hi:.2f}/@ observada em '
                       f'{_n} painéis')
            _valor  = (f'{_delta:+.1f}% acima do teto · R$ '
                       f'{_coe.get("coe_calculado", 0):.2f}/@ contra teto de '
                       f'R$ {_hi:.2f}/@')
        else:
            _contra = (f'a referência de R$ {_coe.get("coe_referencia", 0):.2f}/@ '
                       f'({_coe.get("local_ref") or "a praça"})')
            _valor  = (f'{_delta:+.1f}% · R$ {_coe.get("coe_calculado", 0):.2f}/@ '
                       f'contra R$ {_coe.get("coe_referencia", 0):.2f}/@')

        conclusao.setdefault('memoria', []).append({
            'passo':   'Custo acima da referência da praça',
            'valor':   _valor,
            'detalhe': (f'O custo aplicado está {_delta:.1f}% acima de {_contra} '
                        f'({_coe.get("fonte") or "Campo Futuro/CNA"}; painel mais '
                        f'próximo: {_coe.get("local_ref") or "n/d"}). A comparação é '
                        f'de COE contra COE — custo de desembolso, incluindo compra '
                        f'de animais, sem depreciação nem remuneração do capital. '
                        f'Confira o custo antes de aceitar esta conclusão: se ele '
                        f'estiver superestimado, a geração de caixa e o DSCR estão '
                        f'subestimados na mesma proporção.'),
        })
        conclusao['custo_fora_da_referencia'] = {
            'delta_pct':  round(_delta, 1),
            'calculado':  _coe.get('coe_calculado'),
            'referencia': _coe.get('coe_referencia'),
            'faixa':      _faixa,
            'n_paineis':  _n,
            'local':      _coe.get('local_ref'),
            'fonte':      _coe.get('fonte'),
        }

    if _motivos:
        if conclusao['recomendacao'] == 'aprovar':
            conclusao = dict(
                conclusao, recomendacao='ressalva',
                justificativa=conclusao['justificativa'] + ' Rebaixado: '
                + '; '.join(m[0] for m in _motivos) + '.')
        conclusao.setdefault('memoria', []).extend(m[1] for m in _motivos)

    # ── Proveniência dos parâmetros ─────────────────────────────────────────
    # Cada número usado carrega de onde veio. Medição se cita, política se
    # discute, referência se questiona, declaração se confere — e o comitê
    # precisa saber qual é qual antes de decidir.
    from services.parametros_zootecnicos import (
        DESFRUTE_PCT, NATALIDADE_PCT, DESMAME_PCT, MORTALIDADE_PCT,
        MORTALIDADE_ADULTO_PCT, MORTALIDADE_BEZERRA_PCT,
        RENDIMENTO_CARCACA_PCT, GANHO_ARROBA_MES,
        # Primeiras medições de terceiro do projeto (Embrapa Gado de Corte).
        IDADE_PRIMEIRA_PARICAO_MESES, TAXA_PRENHEZ_MEDIDA_PCT,
        PESO_DESMAMA_MACHO_KG, PESO_DESMAMA_FEMEA_KG,
        PESO_FEMEA_REPOSICAO_KG,
    )
    from services.garantia import DESAGIO_PADRAO, LTV_APROVAR, LTV_RESSALVA
    from services.endividamento import COMPROMETIMENTO_ALERTA

    _cat = catalogo(
        DSCR_APROVAR, DSCR_RESSALVA,
        LTV_APROVAR, LTV_RESSALVA, DESAGIO_PADRAO,
        COMPROMETIMENTO_ALERTA,
        DESFRUTE_PCT,
        NATALIDADE_PCT, DESMAME_PCT, MORTALIDADE_PCT,
        MORTALIDADE_ADULTO_PCT, MORTALIDADE_BEZERRA_PCT,
        RENDIMENTO_CARCACA_PCT, GANHO_ARROBA_MES,
        # Não substituem os parâmetros de projeção — entram para o parecer
        # mostrar contra o que a projeção está ancorada, e para o contador de
        # proveniência deixar de reportar "0 medidos".
        IDADE_PRIMEIRA_PARICAO_MESES, TAXA_PRENHEZ_MEDIDA_PCT,
        PESO_DESMAMA_MACHO_KG, PESO_DESMAMA_FEMEA_KG,
        PESO_FEMEA_REPOSICAO_KG,
    )
    proveniencia = {'parametros': _cat, 'resumo': _resumo_prov(_cat)}

    return {
        'secoes': ['identificacao', 'composicao', 'indicadores',
                   'consistencia', 'financeiro', 'precos_regional',
                   'fluxo_gep', 'garantia', 'endividamento', 'sensibilidade',
                   'shap_explicacao', 'proveniencia', 'conclusao'],
        'identificacao': identificacao,
        'composicao': composicao,
        'indicadores': {'valores': indicadores, 'benchmarks': benchmarks},
        'consistencia': consistencia,
        'financeiro': financeiro,
        'precos_regional': precos_regional,
        'proveniencia': proveniencia,
        'fluxo_gep': fluxo_gep,
        'garantia': garantia,
        'endividamento': endividamento,
        'sensibilidade': sensibilidade,
        'shap_explicacao': shap_explicacao or {},
        'conclusao': conclusao,
    }
