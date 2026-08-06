"""
Proveniência: de onde cada número do parecer vem.

O parecer é cheio de números que aparecem iguais na tela — são só floats. Mas
um deságio de 35% é POLÍTICA (a instituição escolheu, e pode mudar), um
desfrute de 21,7% seria MEDIÇÃO (o IBGE apurou, e se cita), uma natalidade de
70% é REFERÊNCIA (bibliografia, não apurada nesta fazenda) e um custo digitado
é DECLARAÇÃO (informada, não verificada).

Confundir os quatro é o que faz um parecer não se sustentar em comitê.

O requisito de projeto que estes testes protegem: `Parametro` herda de `float`,
então o motor de simulação inteiro continua fazendo aritmética sem saber que o
número tem etiqueta. Se isso quebrar, a camada vira refatoração de mil linhas.
"""
import json

import pytest

from services.proveniencia import (
    Parametro, MEDIDO, REFERENCIA, POLITICA, DECLARADO, ORIGENS,
    medido, referencia, politica, declarado, catalogo, resumo, e_parametro,
)


# ── O requisito que sustenta o desenho ──────────────────────────────────────
def test_parametro_e_float_para_todos_os_efeitos():
    """
    Se isto falhar, toda fórmula do projeto precisa ser reescrita. É o motivo
    de `Parametro` herdar de float em vez de ser um dataclass.
    """
    p = referencia(70.0, 'Benchmark nacional')
    assert isinstance(p, float)
    assert p == 70.0
    assert p * 2 == 140.0
    assert p / 2 == 35.0
    assert p > 65 and p < 75
    assert round(p) == 70
    assert f'{p:.1f}' == '70.0'
    assert sum([p, p]) == 140.0
    assert min(p, 80.0) == 70.0


def test_serializa_como_numero_em_json():
    """O parecer trafega em JSON — a etiqueta não pode virar erro de encoding."""
    assert json.dumps({'nat': referencia(70.0, 'x')}) == '{"nat": 70.0}'


def test_aritmetica_devolve_float_puro():
    """
    O resultado de uma conta entre parâmetros não herda a proveniência de
    nenhum deles — seria mentira dizer que o produto de dois é "medido".
    """
    a = medido(2.0, 'IBGE')
    b = politica(3.0)
    assert not e_parametro(a * b)


# ── As quatro origens ───────────────────────────────────────────────────────
def test_as_quatro_origens_existem():
    assert set(ORIGENS) == {MEDIDO, REFERENCIA, POLITICA, DECLARADO}


def test_origem_invalida_e_recusada():
    with pytest.raises(ValueError, match='origem inválida'):
        Parametro(1.0, origem='chute')


def test_medicao_sem_fonte_e_recusada():
    """
    Medição sem fonte não é medição — é referência com pretensão, e é
    exatamente o tipo de coisa que derruba um parecer no comitê.
    """
    with pytest.raises(ValueError, match='exige `fonte`'):
        medido(21.7, '')


def test_referencia_pode_nao_ter_fonte():
    """Nem toda calibração tem citação — o que ela não pode é se dizer medida."""
    p = referencia(0.83)
    assert p.origem == REFERENCIA


# ── Descrição legível ───────────────────────────────────────────────────────
def test_descricao_traz_fonte_uf_e_ano():
    p = medido(21.7, 'IBGE · PPM tab. 3939 ÷ Abate tab. 1092', ano=2024, uf='MT')
    d = p.descrever()
    assert 'Medido' in d and 'IBGE' in d and 'MT' in d and '2024' in d


def test_descricao_de_politica_nao_inventa_recorte():
    d = politica(1.30, 'Política de crédito da instituição').descrever()
    assert d == 'Política — Política de crédito da instituição'


# ── Catálogo ────────────────────────────────────────────────────────────────
def test_catalogo_percorre_dicts_e_ignora_floats_comuns():
    cat = catalogo(
        {'a': referencia(1.0, 'ref'), 'b': 2.0, 'c': politica(3.0)},
        medido(4.0, 'IBGE'),
        [5.0, declarado(6.0)],
    )
    assert len(cat) == 4, 'floats comuns não podem entrar no catálogo'


def test_catalogo_ordena_por_peso_do_argumento():
    """
    Medição primeiro, declaração por último — é a ordem em que o comitê lê,
    da afirmação mais forte para a mais frágil.
    """
    cat = catalogo(declarado(1.0, rotulo='d'), politica(2.0, rotulo='c'),
                   referencia(3.0, 'x', rotulo='b'), medido(4.0, 'IBGE', rotulo='a'))
    assert [d['origem'] for d in cat] == [MEDIDO, REFERENCIA, POLITICA, DECLARADO]


def test_catalogo_usa_a_chave_do_dict_quando_falta_rotulo():
    cat = catalogo({'Taxa de natalidade': referencia(70.0, 'ref')})
    assert cat[0]['rotulo'] == 'Taxa de natalidade'


def test_rotulo_proprio_vence_a_chave_do_dict():
    cat = catalogo({'chave': referencia(70.0, 'ref', rotulo='Rótulo explícito')})
    assert cat[0]['rotulo'] == 'Rótulo explícito'


def test_catalogo_nao_repete_o_mesmo_parametro():
    p = politica(1.30, 'x', rotulo='DSCR')
    assert len(catalogo(p, p, {'DSCR': p})) == 1


# ── Resumo ──────────────────────────────────────────────────────────────────
def test_resumo_conta_por_origem():
    cat = catalogo(medido(1.0, 'IBGE', rotulo='a'), referencia(2.0, 'x', rotulo='b'),
                   referencia(3.0, 'y', rotulo='c'), politica(4.0, rotulo='d'))
    r = resumo(cat)
    assert r['contagem'] == {MEDIDO: 1, REFERENCIA: 2, POLITICA: 1, DECLARADO: 0}
    assert r['total'] == 4
    assert r['medidos_pct'] == 25.0


def test_resumo_de_catalogo_vazio_nao_divide_por_zero():
    assert resumo([])['medidos_pct'] == 0.0


# ── Estado real do projeto ──────────────────────────────────────────────────
def test_os_parametros_do_projeto_estao_etiquetados():
    from services.parametros_zootecnicos import DESFRUTE_PCT, NATALIDADE_PCT
    from services.parecer_credito import DSCR_APROVAR
    from services.garantia import DESAGIO_PADRAO, LTV_APROVAR
    from services.endividamento import COMPROMETIMENTO_ALERTA

    assert e_parametro(NATALIDADE_PCT)
    assert e_parametro(DESFRUTE_PCT['CRIA'])
    assert e_parametro(DSCR_APROVAR)
    assert e_parametro(LTV_APROVAR)
    assert e_parametro(DESAGIO_PADRAO['bois'])
    assert e_parametro(COMPROMETIMENTO_ALERTA)


def test_politica_de_credito_nao_se_disfarca_de_referencia():
    """
    DSCR, LTV, deságio e comprometimento são escolhas da instituição. Marcá-los
    como referência sugeriria que descrevem um fato — e eles não descrevem.
    """
    from services.parecer_credito import DSCR_APROVAR, DSCR_RESSALVA
    from services.garantia import DESAGIO_PADRAO, LTV_APROVAR, LTV_RESSALVA
    from services.endividamento import COMPROMETIMENTO_ALERTA

    for p in (DSCR_APROVAR, DSCR_RESSALVA, LTV_APROVAR, LTV_RESSALVA,
              COMPROMETIMENTO_ALERTA, *DESAGIO_PADRAO.values()):
        assert p.origem == POLITICA, f'{p.rotulo} marcado como {p.origem}'


def test_nada_no_projeto_se_diz_medido_ainda():
    """
    Guarda de honestidade. Hoje o projeto não tem NENHUMA série apurada por
    terceiro — tudo é referência ou política. No dia em que o IBGE entrar, este
    teste falha e deve ser reescrito com a fonte real.
    """
    from services.parametros_zootecnicos import DESFRUTE_PCT, NATALIDADE_PCT
    from services.garantia import DESAGIO_PADRAO

    todos = catalogo(DESFRUTE_PCT, NATALIDADE_PCT, DESAGIO_PADRAO)
    assert all(d['origem'] != MEDIDO for d in todos), (
        'algum parâmetro passou a se dizer medido — confira se a fonte é real '
        'e atualize este teste'
    )


def test_o_parecer_carrega_a_proveniencia():
    from services.parecer_credito import montar_parecer
    p = montar_parecer(
        identificacao={}, composicao={}, indicadores={}, benchmarks=[],
        consistencia={}, financeiro={}, geracao_caixa_anual=900_000,
        credito={'credito_valor': 500_000, 'prazo_meses': 36,
                 'juros_aa': 0.125, 'carencia_meses': 0, 'dividas_mensais': 0},
        projecao_anos=[{'ano': a, 'dscr': 3.0, 'viavel': True} for a in (1, 2, 3)])

    assert 'proveniencia' in p['secoes']
    pv = p['proveniencia']
    assert pv['parametros'], 'o parecer saiu sem catálogo de parâmetros'
    assert pv['resumo']['total'] == len(pv['parametros'])
    for d in pv['parametros']:
        assert d['rotulo'], 'parâmetro sem rótulo não diz nada ao analista'
        assert d['origem'] in ORIGENS
