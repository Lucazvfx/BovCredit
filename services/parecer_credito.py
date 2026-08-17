"""Parecer de crédito: capacidade de pagamento (Price + DSCR) e montagem.

Módulo puro — não importa Flask nem DB. Recebe números já computados.
"""
from __future__ import annotations

import os

from services.proveniencia import (
    politica, catalogo, do_modulo, resumo as _resumo_prov)

# Faixas de política de crédito (DSCR) — ajustáveis, não são benchmark
# zootécnico. Marcadas como POLÍTICA na proveniência: em comitê elas se
# discutem, não se citam.
DSCR_APROVAR = politica(
    1.30, 'Política de crédito da instituição', rotulo='DSCR para aprovar',
    nota='Cobertura mínima do serviço da dívida no ano crítico do prazo.')
DSCR_RESSALVA = politica(
    1.00, 'Política de crédito da instituição', rotulo='DSCR para ressalva')


_CARENCIA_SEM_CAP = os.environ.get('CARENCIA_SEM_CAPITALIZACAO', '0') == '1'


# ── Matemática de amortização: uma cópia só ─────────────────────────────────
#
# Estas quatro funções existiam DUPLICADAS aqui e em
# payment_capacity_engine/dscr.py — mesma matemática, diferindo só em aspas e
# quebra de linha. app.py importava a daqui; o motor usava a de lá.
#
# Duas cópias da mesma conta é a classe de defeito que já apareceu três vezes
# nesta base (base reprodutiva, faixa 0–12, motores de recria): elas não
# divergem no dia em que nascem, divergem no dia em que alguém corrige uma
# só. Acrescentar SAC teria criado a quarta e a quinta cópia.
#
# O motor é a fonte; aqui ficam só os nomes que já eram importados.
from services.payment_capacity_engine.dscr import (  # noqa: E402
    PRICE,
    SAC,
    SISTEMAS,
    cronograma_divida,
    cronograma_price,
    credito_maximo,
    parcela_price,
    parcelas_sac,
    principal_apos_carencia,
)


def avaliar_capacidade_pagamento(
    geracao_caixa_anual: float,
    credito_valor: float,
    prazo_meses: int,
    juros_aa: float,
    carencia_meses: int = 0,
    dividas_mensais: float = 0.0,
    sistema: str = PRICE,
) -> dict:
    from services.payment_capacity_engine import calculate_payment_capacity

    result = calculate_payment_capacity(
        {
            'geracao_caixa_anual': geracao_caixa_anual,
            'projecao_anos': [{'ano': 1, 'resultado': geracao_caixa_anual}],
        },
        {
            'credito_valor': credito_valor,
            'prazo_meses': prazo_meses,
            'juros_aa': juros_aa,
            'carencia_meses': carencia_meses,
            'sistema_amortizacao': sistema,
        },
        {'parcela_existente_mensal': dividas_mensais},
    )
    return result['legacy']


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
    if not projecao_anos:
        return base
    if not base.get('cronograma_divida') and not base.get('parcela_mensal'):
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
        'passo': 'Serviço da dívida',
        'valor': 'cronograma anual',
        'detalhe': ('O DSCR usa os vencimentos efetivos de cada ano; não '
                    'multiplica automaticamente a parcela por doze.'),
    }]
    for item in base.get('cronograma_divida') or []:
        memoria.append({
            'passo': f'Serviço da nova operação — ano {item["ano"]}',
            'valor': _fmt_rs(item['servico_nova_operacao']),
            'detalhe': (f'{item["parcelas_nova_operacao"]} parcela(s) de '
                        f'{_fmt_rs(base["parcela_mensal"])}; carência e ano '
                        'parcial respeitados.'),
        })
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

    recomendacao_ano1 = base.get('recomendacao')
    rebaixado = recomendacao_ano1 is not None and rec != recomendacao_ano1
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
            'valor':   f'{recomendacao_ano1.upper()} → {rec.upper()}',
            'detalhe': f'O ano 1 isolado indicava {recomendacao_ano1} '
                       f'(DSCR {base["dscr"]:.2f}), mas ele liquida o estoque '
                       f'acumulado e não se repete.',
        })

    base.update({
        'recomendacao':      rec,
        'faixa':             rec,
        'justificativa':     just,
        'dscr_ano1':         next((d for ano, d in dscrs if ano == 1), None),
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
        dividas_mensais=_f(credito.get('dividas_mensais')),
        sistema=credito.get('sistema_amortizacao'))

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
    # O CUSTO DO ANO QUE SUSTENTA A RECOMENDAÇÃO, não o do ano 1.
    #
    # O benchmark de custo era medido só no ano 1 — o mesmo ano que este módulo
    # documenta como enganoso porque liquida o estoque declarado. Numa cria de
    # 1.775 cabeças isso dava R$ 191,17/@ no ano 1 (dentro da faixa medida de
    # 166–223) e R$ 292,74/@ no ano 3 (+31% acima do teto). O parecer negava
    # pelo ano crítico e, ao lado, dizia que o custo estava na praça.
    _ano_critico = conclusao.get('ano_critico')
    _coe = {}
    if _ano_critico:
        _coe = next((a.get('coe_benchmark') or {} for a in (projecao_anos or [])
                     if a.get('ano') == _ano_critico), {})
    if not _coe:
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

        # Perímetro parcial — recria ou engorda isolada contra painel que cobre
        # as duas fases e vende boi terminado. O aviso CONTINUA, porque o que
        # ele pede ("confira o custo") vale de todo jeito; o que muda é que o
        # texto para de atribuir o desvio inteiro ao custo. Calar o aviso
        # perderia o sinal que motivou o recurso; afirmar "110% acima da praça"
        # afirmaria o que não se sabe.
        _parcial = _coe.get('perimetro_parcial')
        if _parcial:
            _passo   = 'Custo alto, sem referência direta'
            _detalhe = (
                f'O custo aplicado está {_delta:.1f}% acima de {_contra} '
                f'({_coe.get("fonte") or "Campo Futuro/CNA"}), mas os dois lados '
                f'NÃO são o mesmo produto: {_parcial}. Parte do desvio é '
                f'perímetro, e não dá para separar quanto. Confira o custo pela '
                f'sua própria série antes de aceitar esta conclusão: se ele '
                f'estiver superestimado, a geração de caixa e o DSCR estão '
                f'subestimados na mesma proporção.')
        else:
            _passo   = 'Custo acima da referência da praça'
            _detalhe = (
                f'O custo aplicado está {_delta:.1f}% acima de {_contra} '
                f'({_coe.get("fonte") or "Campo Futuro/CNA"}; painel mais '
                f'próximo: {_coe.get("local_ref") or "n/d"}). A comparação é '
                f'de COE contra COE — custo de desembolso operacional, incluindo '
                f'compra de animais, sem investimento, depreciação nem '
                f'remuneração do capital. Confira o custo antes de aceitar esta '
                f'conclusão: se ele estiver superestimado, a geração de caixa e '
                f'o DSCR estão subestimados na mesma proporção.')

        conclusao.setdefault('memoria', []).append({
            'passo': _passo, 'valor': _valor, 'detalhe': _detalhe,
        })
        conclusao['custo_fora_da_referencia'] = {
            'delta_pct':  round(_delta, 1),
            'calculado':  _coe.get('coe_calculado'),
            'referencia': _coe.get('coe_referencia'),
            'faixa':      _faixa,
            'n_paineis':  _n,
            'local':      _coe.get('local_ref'),
            'perimetro_parcial': _parcial,
            'atribuivel': _parcial is None,
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
    import services.parametros_zootecnicos as _pz
    import services.nivel_tecnologico as _nt

    _cat = catalogo(
        DSCR_APROVAR, DSCR_RESSALVA,
        LTV_APROVAR, LTV_RESSALVA, DESAGIO_PADRAO,
        COMPROMETIMENTO_ALERTA,
        # ── Zootecnia: varrida do módulo, não listada à mão ──────────────────
        #
        # Esta lista ERA escrita à mão, e toda medição registrada depois dela
        # ficava invisível. Um parecer de produção publicava CINCO parâmetros
        # medidos quando o módulo já tinha TREZE: as quatro do painel do
        # Pantanal e as quatro da cadeia reprodutiva de Vieira et al. nunca
        # chegaram ao documento.
        #
        # O rodapé de proveniência é o que separa este parecer de uma planilha
        # com opinião. Uma medição que não aparece nele é, para o comitê, uma
        # medição que não existe — e o defeito era silencioso: nada quebrava,
        # o número só ficava menor que a verdade.
        #
        # Mesma família das três cópias das faixas de desfrute: duas fontes da
        # mesma informação sincronizadas à mão, e uma fica para trás. Agora há
        # uma fonte só, e registrar um `medido()` basta para ele ser publicado.
        do_modulo(_pz, _nt),
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
