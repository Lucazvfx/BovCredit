"""Parecer de crédito: capacidade de pagamento (Price + DSCR) e montagem.

Módulo puro — não importa Flask nem DB. Recebe números já computados.
"""
from __future__ import annotations

import os

from services.proveniencia import (
    catalogo, do_modulo, e_parametro, resumo as _resumo_prov)


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
# O motor é a fonte; aqui ficam só os nomes que já eram importados — inclusive
# DSCR_APROVAR/DSCR_RESSALVA (assistente e testes importam daqui). Não redefinir.
# avaliar_capacidade_no_prazo também estava duplicada aqui e seguiu o mesmo caminho.
from services.payment_capacity_engine.dscr import (  # noqa: E402
    DSCR_APROVAR,
    DSCR_RESSALVA,
    MENSAL,
    PERIODICIDADES,
    PRICE,
    SAC,
    SISTEMAS,
    avaliar_capacidade_no_prazo,
    cronograma_divida,
    cronograma_price,
    credito_maximo,
    parcela_price,
    parcelas_sac,
    principal_apos_carencia,
)
from services.payment_capacity_engine.ciclo_pecuario import (  # noqa: E402
    projetar_fluxo_ciclo,
)
from services.stress_engine.pecuaria import (  # noqa: E402
    _MAX_VALOR as _ESTRESSE_MAX, _MIN_POSITIVO as _ESTRESSE_MIN, _numero,
    CENARIOS_PECUARIOS, BasePecuaria, simular_cenarios_pecuarios,
    ponto_ruptura_arroba,
)


def avaliar_capacidade_pagamento(
    geracao_caixa_anual: float,
    credito_valor: float,
    prazo_meses: int,
    juros_aa: float,
    carencia_meses: int = 0,
    dividas_mensais: float = 0.0,
    sistema: str = PRICE,
    periodicidade_meses: int = MENSAL,
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
            'periodicidade_meses': periodicidade_meses,
        },
        {'parcela_existente_mensal': dividas_mensais},
    )
    return result['legacy']


# Divergência do COE frente à referência da praça a partir da qual o parecer
# avisa. Limiar de política nosso, não norma: abaixo disso a diferença cabe em
# variação de sistema e de região; acima, o custo passa a ser candidato mais
# provável a causa da recusa do que a fazenda.
COE_DIVERGENCIA_AVISO = 25.0


_PAGAMENTOS_ANO = {'mensal': 12, 'semestral': 2, 'anual': 1}


def _fluxo_ciclo_do_parecer(*, sistema_produtivo, frequencia_pagamento,
                            capital_giro_inicial, conclusao, projecao_anos):
    """Fluxo sazonal do ANO CRÍTICO, com os mesmos números do DSCR do parecer.

    Receita, resultado e serviço da dívida saem da linha de `projecao_anos` do
    ano crítico — a mesma que sustenta `conclusao['dscr_minimo']`. O custo
    operacional é `receita − resultado`, de modo que (receita − custo) é
    exatamente o numerador do DSCR (inclui a reposição de reprodutores). A
    parcela é o serviço anual daquele ano ÷ pagamentos por ano da frequência:
    o serviço anual não muda, só o calendário.
    """
    base = {'disponivel': False, 'sistema_produtivo': sistema_produtivo,
            'frequencia_pagamento': frequencia_pagamento}
    if not projecao_anos:
        return {**base, 'motivo': 'Sem projeção por ano para derivar receita e custo.'}
    linha = _linha_ano_critico(conclusao, projecao_anos)
    try:
        receita = float(linha['receita'])
        resultado = float(linha['resultado'])
        servico = float(linha.get('servico_divida_anual') or 0.0)
    except (KeyError, TypeError, ValueError):
        return {**base, 'motivo': 'Projeção do ano crítico incompleta.'}
    custo = receita - resultado
    try:
        r = projetar_fluxo_ciclo(
            sistema=sistema_produtivo,
            receita_anual=receita,
            custo_operacional_anual=custo,
            parcela_divida=servico / _PAGAMENTOS_ANO[frequencia_pagamento],
            frequencia=frequencia_pagamento,
            capital_giro_inicial=capital_giro_inicial)
    except ValueError as e:
        # Resultado maior que a receita (custo negativo) ou valor fora do limite.
        return {**base, 'motivo': f'Fluxo sazonal indisponível: {e}'}
    # O parecer aprova pelo DSCR ARREDONDADO a 2 casas (1,2996 -> 1,30); o motor
    # compara o valor exato. Na faixa [1,295; 1,30) os dois discordariam e o
    # alerta sumiria sob um APROVAR. O alerta segue o veredito que o analista lê.
    dscr_parecer = linha.get('dscr')
    if dscr_parecer is not None and servico > 0:
        ok = float(dscr_parecer) >= DSCR_APROVAR
        if ok != r['dscr_anual_suficiente']:
            r['dscr_anual_suficiente'] = ok
            r['quebra_caixa_com_dscr_ok'] = bool(
                ok and r['meses_deficit_por_divida'])
            r['justificativa'] = list(r['justificativa']) + [
                f"DSCR do parecer ({float(dscr_parecer):.2f}, arredondado) é a "
                f"referência da aprovação; a conta exata do fluxo difere na "
                f"segunda casa."]
    return {**r, 'disponivel': True, 'ano_referencia': linha.get('ano'),
            'receita_anual': round(receita, 2),
            'custo_operacional_anual': round(custo, 2),
            'servico_divida_anual_parecer': round(servico, 2),
            'capital_giro_inicial': capital_giro_inicial}


CAMPOS_ESTRESSE_PECUARIO = ('preco_arroba_base', 'custo_reposicao_anual',
                            'custo_suplementacao_anual')


def validar_entrada_estresse_pecuario(entrada: dict) -> dict:
    """Valida os 3 campos do estresse pecuário; ValueError com mensagem clara.

    Usa o mesmo validador e os mesmos tetos de `stress_engine.pecuaria`
    (rejeita texto, bool, negativo, NaN, inf e int gigante tipo 10**400).
    O preço da arroba é obrigatoriamente > 0: o volume é derivado dele.
    """
    ausentes = [c for c in CAMPOS_ESTRESSE_PECUARIO
                if entrada.get(c) in (None, '')]
    if ausentes:
        raise ValueError('Estresse pecuário exige os três campos juntos; '
                         'faltando: ' + ', '.join(ausentes) + '.')
    preco = _numero(entrada['preco_arroba_base'], 'preco_arroba_base',
                    minimo=_ESTRESSE_MIN, maximo=_ESTRESSE_MAX)
    return {
        'preco_arroba_base': preco,
        'custo_reposicao_anual': _numero(
            entrada['custo_reposicao_anual'], 'custo_reposicao_anual',
            minimo=0.0, maximo=_ESTRESSE_MAX),
        'custo_suplementacao_anual': _numero(
            entrada['custo_suplementacao_anual'], 'custo_suplementacao_anual',
            minimo=0.0, maximo=_ESTRESSE_MAX),
    }


def _linha_ano_critico(conclusao, projecao_anos):
    ano = conclusao.get('ano_critico')
    return next((a for a in projecao_anos if a.get('ano') == ano), None) \
        or projecao_anos[0]


def _estresse_pecuario_do_parecer(*, entrada, conclusao, projecao_anos):
    """Estresse pecuário do ANO CRÍTICO, com os números do DSCR do parecer.

    Receita, resultado e serviço da dívida saem da mesma linha de
    `projecao_anos` que sustenta `conclusao['dscr_minimo']`; custo total =
    receita − resultado. O analista informa preço da arroba, reposição e
    suplementação; `custo_outros` é o resíduo e o volume é a receita dividida
    pelo preço (arrobas EQUIVALENTES: toda a receita do ano é tratada como
    venda de arrobas). Assim o DSCR-base do motor é igual ao do parecer.
    """
    base = {'disponivel': False, 'entrada': dict(entrada)}
    if not projecao_anos:
        return {**base, 'motivo': 'Sem projeção por ano para derivar a base do estresse.'}
    linha = _linha_ano_critico(conclusao, projecao_anos)
    try:
        receita = float(linha['receita'])
        resultado = float(linha['resultado'])
        servico = float(linha.get('servico_divida_anual') or 0.0)
        preco = entrada['preco_arroba_base']
        custo = receita - resultado
        outros = custo - entrada['custo_reposicao_anual'] \
            - entrada['custo_suplementacao_anual']
        if custo < 0:
            return {**base, 'motivo': 'Resultado do ano crítico maior que a '
                    'receita: custo operacional negativo.'}
        if outros < -1e-6 * max(1.0, abs(custo)):
            return {**base, 'motivo': 'Reposição + suplementação informadas '
                    'excedem o custo operacional do ano crítico.'}
        b = BasePecuaria(
            arrobas_vendidas=receita / preco, preco_arroba=preco,
            custo_reposicao=entrada['custo_reposicao_anual'],
            custo_suplementacao=entrada['custo_suplementacao_anual'],
            custo_outros=max(outros, 0.0), servico_divida=servico)
        res = simular_cenarios_pecuarios(b)
        pr = ponto_ruptura_arroba(b)
    except (KeyError, TypeError, ValueError, OverflowError) as e:
        return {**base, 'motivo': f'Estresse pecuário indisponível: {e}'}

    def _res(r):
        return {'receita': r.receita, 'custo': r.custo,
                'resultado': r.resultado, 'margem_liquida': r.margem_liquida,
                'dscr': r.dscr, 'classificacao': r.classificacao}

    ref = res['base']
    cenarios = {}
    for nome, r in res.items():
        if nome == 'base':
            continue
        ch = CENARIOS_PECUARIOS[nome]
        d = _res(r)
        d['descricao'] = ch.descricao
        d['impacto_margem_pp'] = (
            None if r.margem_liquida is None or ref.margem_liquida is None
            else (r.margem_liquida - ref.margem_liquida) * 100.0)
        d['premissas'] = {
            c: (getattr(ch, c).para_dict() if e_parametro(getattr(ch, c))
                else float(getattr(ch, c)))
            for c in ('arroba_pct', 'reposicao_pct', 'suplementacao_pct',
                      'volume_pct')}
        cenarios[nome] = d

    def _rup(x):
        return {'dscr_alvo': x.dscr_alvo, 'status': x.status,
                'preco_base': x.preco_base, 'preco_minimo': x.preco_minimo,
                'queda_maxima_suportada_pct': x.margem_seguranca_pct,
                'em_ruptura': x.em_ruptura}

    # O parecer decide pelo DSCR ARREDONDADO a 2 casas; o estresse usa o exato.
    # Na faixa de arredondamento (ex.: 1,297 -> 1,30) os dois discordam: os
    # números do motor não são alterados, mas a divergência é dita no bloco.
    avisos = []
    dscr_p = linha.get('dscr')
    if dscr_p is not None and servico > 0:
        dscr_p = float(dscr_p)
        cls_p = ('aprovar' if dscr_p >= DSCR_APROVAR
                 else 'ressalva' if dscr_p >= DSCR_RESSALVA else 'negar')
        if cls_p != ref.classificacao:
            avisos.append(
                f"DSCR do parecer ({dscr_p:.2f}, arredondado) classifica como "
                f"'{cls_p}'; a conta exata do estresse ({ref.dscr:.4f}) "
                f"classifica a base como '{ref.classificacao}'. O veredito do "
                f"parecer vale; o ponto de ruptura usa a conta exata.")
    return {**base, 'avisos': avisos, 'disponivel': True, 'ano_referencia': linha.get('ano'),
            'base': {**_res(ref), 'arrobas_equivalentes': b.arrobas_vendidas,
                     'preco_arroba': b.preco_arroba,
                     'custo_reposicao': b.custo_reposicao,
                     'custo_suplementacao': b.custo_suplementacao,
                     'custo_outros': b.custo_outros,
                     'servico_divida_anual': b.servico_divida,
                     'dscr_parecer': linha.get('dscr')},
            'cenarios': cenarios,
            'ponto_ruptura_arroba': {'aprovar': _rup(pr.aprovar),
                                     'ressalva': _rup(pr.ressalva)},
            'limiares_dscr': {
                'aprovar': (DSCR_APROVAR.para_dict()
                            if e_parametro(DSCR_APROVAR) else float(DSCR_APROVAR)),
                'ressalva': (DSCR_RESSALVA.para_dict()
                             if e_parametro(DSCR_RESSALVA) else float(DSCR_RESSALVA))},
            'premissas_base': ('Volume = receita do ano crítico ÷ preço da '
                               'arroba (arrobas equivalentes); outros custos '
                               '= custo total − reposição − suplementação; '
                               'a reposição não cai com o volume.')}


def montar_parecer(*, identificacao, composicao, indicadores, benchmarks,
                   consistencia, financeiro, geracao_caixa_anual, credito,
                   fluxo_gep=None, sensibilidade=None, shap_explicacao=None,
                   projecao_anos=None, garantia=None, endividamento=None,
                   precos_regional=None, sistema_produtivo=None,
                   frequencia_pagamento='mensal',
                   capital_giro_inicial=0.0,
                   estresse_pecuario_entrada=None) -> dict:
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
        sistema=credito.get('sistema_amortizacao'),
        periodicidade_meses=credito.get('periodicidade_meses'))

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

    # Só quando o analista informa o sistema produtivo: sem ele o parecer sai
    # idêntico ao de antes (mesmas chaves, mesma lista de seções).
    ciclo_pecuario = (_fluxo_ciclo_do_parecer(
        sistema_produtivo=sistema_produtivo,
        frequencia_pagamento=frequencia_pagamento,
        capital_giro_inicial=capital_giro_inicial,
        conclusao=conclusao, projecao_anos=projecao_anos)
        if sistema_produtivo else None)

    # Só quando o analista informa os três campos do estresse pecuário.
    estresse_pecuario = (_estresse_pecuario_do_parecer(
        entrada=estresse_pecuario_entrada, conclusao=conclusao,
        projecao_anos=projecao_anos)
        if estresse_pecuario_entrada else None)

    resultado = {
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
    if ciclo_pecuario is not None:
        resultado['ciclo_pecuario'] = ciclo_pecuario
    if estresse_pecuario is not None:
        resultado['estresse_pecuario'] = estresse_pecuario
    return resultado
