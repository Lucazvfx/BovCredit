"""
Duas fontes novas conferem faixas que até aqui só se conferiam contra si mesmas.

PAINEL CORINTO/MG (Tabela 3.5) — a mesma fazenda de ciclo completo por sete
anos, 2005 a 2011, enquanto cresce de 1.460 para 3.980 cabeças. É a única
série TEMPORAL da nossa base; o resto são fotografias de fazendas diferentes
num ano só, e fotografia não mostra oscilação.

EXAGRO 2013 (Tabela 3.9) — 71 fazendas comerciais do bioma amazônico,
exclusivamente a pasto. Confere os limiares de lotação contra fazenda de
verdade, e não contra média nacional de bibliografia.
"""
import pytest

from services.benchmarks_nacionais import (
    DESFRUTE_MODALIDADE, PAINEL_CORINTO_MG,
    EXAGRO_LOTACAO_2013, EXAGRO_LOTACAO_MEDIA_UA_HA,
    EXAGRO_LOTACAO_MEDIANA_UA_HA,
)
from services.nivel_tecnologico import (
    LOTACAO_MEDIA_BR, LOTACAO_INTENSIVO, nivel_por_lotacao, EXTENSIVO, MEDIO,
)
from services.parametros_zootecnicos import PRENHEZ_PCT


# ── Corinto: a faixa de desfrute tem de conter a série inteira ──────────────
def test_a_faixa_de_ciclo_completo_cobre_os_sete_anos():
    """
    Era (21,0 – 45,0) e a série estoura nas DUAS pontas: 16,5% no ano de
    retenção e 49,3% no ano de realização.

    Reprovar os dois extremos seria reprovar a fazenda inteira — inclusive nos
    anos em que ela estava fazendo a coisa certa. Ela terminou o período com
    lucro operacional de R$ 341/ha contra R$ 4,97 no primeiro ano.
    """
    lo, hi = DESFRUTE_MODALIDADE['CICLO_COMPLETO']
    desfrutes = [linha[4] for linha in PAINEL_CORINTO_MG]
    assert lo <= min(desfrutes), f'piso {lo}% reprova o ano de {min(desfrutes)}%'
    assert hi >= max(desfrutes), f'teto {hi}% reprova o ano de {max(desfrutes)}%'


def test_o_desfrute_de_um_ciclo_completo_real_oscila_muito():
    """
    A propriedade que só uma série temporal mostra, e que justifica uma faixa
    larga em vez de um ponto: a MESMA fazenda varia por um fator de três sem
    ter virado outra coisa.
    """
    d = [linha[4] for linha in PAINEL_CORINTO_MG]
    assert max(d) / min(d) > 2.5, (
        'a série parou de oscilar — se os dados mudaram, a largura da faixa '
        'de ciclo completo precisa ser rediscutida'
    )


def test_a_prenhez_comercial_comeca_muito_abaixo_da_experimental():
    """
    O nosso 87,5% medido é rebanho de pesquisa da Embrapa. Uma fazenda em
    operação começa em 54% e leva cinco anos para chegar a 80%.

    Isso é o que impede de tratar o número da Embrapa como projeção: a faixa
    real de uma fazenda comercial vai de 54 a 91, e nós projetamos um ponto só.
    """
    prenhez = [linha[5] for linha in PAINEL_CORINTO_MG]
    assert min(prenhez) == 54.0
    assert min(prenhez) < float(PRENHEZ_PCT) < max(prenhez), (
        f'a projeção padrão ({float(PRENHEZ_PCT)}%) saiu do intervalo medido '
        f'({min(prenhez)}–{max(prenhez)}%)'
    )


def test_a_mortalidade_cai_com_a_intensificacao():
    """
    De 6,5% para 1,3% na mesma fazenda. Não é constante da espécie — é
    resultado de manejo, e o nosso default único de 3% para todo mundo fica
    registrado aqui como simplificação conhecida.
    """
    mort = [linha[6] for linha in PAINEL_CORINTO_MG]
    assert mort[0] > mort[-1] * 4


# ── EXAGRO: os limiares de lotação contra fazenda comercial ─────────────────
def test_a_mediana_do_exagro_sustenta_o_limiar_de_extensivo():
    """
    71 fazendas comerciais a pasto, mediana de 0,80 UA/ha contra o nosso
    limiar de 0,70. A metade de baixo de um grupo que se submete a
    benchmarking fica logo ACIMA do limiar — que é onde ele deve estar: quem
    cai abaixo dele é extensivo de verdade, não fazenda mediana.
    """
    assert float(LOTACAO_MEDIA_BR) < EXAGRO_LOTACAO_MEDIANA_UA_HA
    assert EXAGRO_LOTACAO_MEDIANA_UA_HA < EXAGRO_LOTACAO_MEDIA_UA_HA


def test_nenhuma_fazenda_do_exagro_cai_em_intensivo():
    """
    O limiar de intensivo (1,6 UA/ha) tem de ser exigente: nenhuma das 71
    fazendas a pasto do bioma amazônico o alcança. Se alguma alcançasse, o
    nível intensivo — que é o mais barato dos perfis de custo — estaria sendo
    dado a fazenda comum, e o erro correria a favor de aprovar.
    """
    for uf, n, area, animais, cab_ha, ua_ha in EXAGRO_LOTACAO_2013:
        assert ua_ha < float(LOTACAO_INTENSIVO), f'{uf}: {ua_ha} UA/ha'
        assert nivel_por_lotacao(ua_ha) in (EXTENSIVO, MEDIO)


def test_a_media_do_exagro_bate_com_as_linhas():
    """A média publicada tem de sair das próprias linhas, ou uma delas está errada."""
    ua = [l[5] for l in EXAGRO_LOTACAO_2013]
    assert sum(ua) / len(ua) == pytest.approx(EXAGRO_LOTACAO_MEDIA_UA_HA, abs=0.06)


# ── A arroba PRODUZIDA, e a hipótese que a medição desmentiu ────────────────
def test_a_producao_em_arroba_detecta_liquidacao():
    """
    O EXAGRO define a produção como (estoque final − inicial) + (vendas −
    compras). A Tabela 3.7 confirma o denominador: custo operacional por
    arroba é sobre a arroba PRODUZIDA, não a vendida.

    CORREÇÃO DE UMA AFIRMAÇÃO MINHA. Eu disse que, em rebanho que cresce,
    produzida > vendida, e que por isso o nosso COE por arroba estaria
    SUPERESTIMADO — que parte do "+31% acima da faixa" seria só denominador.

    Medido, é o contrário: o estoque em arrobas ENCOLHE todo ano na cria, e o
    custo por arroba produzida fica 16 a 31% ACIMA do custo por arroba
    vendida. Trocar o denominador tornaria o parecer mais duro, não mais
    brando.

    Por isso a métrica principal não mudou: no ano 1 a razão explode (+147%),
    porque é o ano que liquida o estoque declarado, e um custo por arroba que
    tende ao infinito não se compara com painel nenhum. O que ela é de fato é
    um DETECTOR DE LIQUIDAÇÃO, em arroba — a unidade em que o crédito pensa.
    """
    import database as db
    from app import app
    db.init_db()
    email = 'produzidas@example.com'
    u = db.buscar_usuario_email(email)
    if not u:
        db.criar_usuario(email, 'Prod', 'senha123')
        u = db.buscar_usuario_email(email)
    app.config['TESTING'] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u['id'])

    CRIA = [300, 280, 200, 80, 100, 40, 150, 10, 600, 15]
    r = c.post('/api/classificar', json={
        'valores': CRIA, 'preco': 330, 'credito_valor': sum(CRIA) * 1200,
        'prazo_meses': 36, 'juros_aa': 0.125}).get_json()
    anos = r['projecao_anos']

    for a in anos:
        assert a['arrobas_produzidas'] is not None
        assert a['producao_sobre_venda_pct'] is not None

    # O ano 1 liquida estoque: produz muito menos do que vende.
    assert anos[0]['producao_sobre_venda_pct'] < 60, (
        'o ano 1 parou de liquidar estoque declarado — se a projeção mudou, '
        'o detector de liquidação precisa ser reavaliado'
    )
    # E nos anos de regime a distância encolhe, mas não some: a cria continua
    # encolhendo em arroba, que é o achado, não um defeito da métrica.
    assert 60 < anos[2]['producao_sobre_venda_pct'] < 100
