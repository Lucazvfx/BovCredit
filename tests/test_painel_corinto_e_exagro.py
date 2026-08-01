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
    EXAGRO_LOTACAO_MEDIANA_UA_HA, EXAGRO_RESULTADO_2013,
    EXAGRO_DISPERSAO_2013, EXAGRO_PRODUCAO_MEDIANA_ARROBA_HA,
    EXAGRO_PIOR_RESULTADO_HA, EXAGRO_MELHOR_RESULTADO_HA,
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


# ── Tabelas 3.10 e 3.11: o resultado econômico das mesmas 71 fazendas ───────
def test_fazenda_comercial_perde_dinheiro_e_nao_e_excecao():
    """
    O achado que mais muda como se lê um parecer negativo daqui.

    Tocantins, com SETE fazendas, fecha 2013 com resultado negativo (−R$ 8/ha)
    e retorno de −6,0%. Individualmente, a pior fazenda da amostra perde
    R$ 270/ha. E são propriedades que se submetem voluntariamente a
    benchmarking — a metade de cima do setor.

    Um modelo que reprova TODA fazenda está errado. Um que reprova uma ficha
    fraca pode estar apenas descrevendo o setor.
    """
    negativos = [e for e in EXAGRO_RESULTADO_2013 if e[6] < 0]
    assert negativos, 'a amostra deixou de ter estado com resultado negativo'
    assert any(e[1] >= 5 for e in negativos), (
        'o estado negativo virou amostra de uma fazenda só — deixa de '
        'sustentar a afirmação de que perder dinheiro não é exceção'
    )
    assert EXAGRO_PIOR_RESULTADO_HA < 0 < EXAGRO_MELHOR_RESULTADO_HA


def test_custo_alto_nao_implica_menos_rentavel():
    """
    Justificativa de terceiro para uma escolha que já era nossa: o desvio de
    custo contra o painel entra como AVISO, não como reprovação.

    Rondônia tem o MAIOR custo por hectare da amostra e, ao mesmo tempo, o
    maior resultado e o maior retorno sobre capital. Reprovar por custo alto
    reprovaria a fazenda mais rentável do grupo.
    """
    mais_caro = max(EXAGRO_RESULTADO_2013, key=lambda e: e[3])
    melhor_rci = max(EXAGRO_RESULTADO_2013, key=lambda e: e[7])
    assert mais_caro[0] == melhor_rci[0] == 'RO', (mais_caro, melhor_rci)

    from services.parecer_credito import COE_DIVERGENCIA_AVISO
    assert COE_DIVERGENCIA_AVISO > 0, (
        'o desvio de custo virou reprovação — ver Rondônia nesta amostra'
    )


def test_a_dispersao_dentro_do_estado_engole_a_media():
    """
    A Tabela 3.11 mostra o que a média esconde: em Mato Grosso, 33 fazendas
    vão de −R$ 94/ha a +R$ 380/ha, com média de R$ 145. Comparar uma fazenda
    contra a média de um estado diz muito menos do que parece.
    """
    for uf, n, media, menor, maior, mediana in EXAGRO_DISPERSAO_2013:
        if menor is None:
            assert n == 1, f'{uf} tem {n} fazendas e nenhuma dispersão publicada'
            continue
        assert menor < media < maior, (uf, menor, media, maior)
        assert (maior - menor) > abs(media), (
            f'{uf}: a amplitude deixou de superar a própria média'
        )


def test_a_produtividade_do_exagro_fica_entre_os_nossos_limiares():
    """
    Mediana de 6,10 @/ha/ano em 71 fazendas comerciais, contra os nossos
    limiares de 4,77 (média nacional Rally) e 12,0 (intensivo). Um grupo de
    benchmarking ficar acima da média nacional e longe do intensivo é
    exatamente o esperado — e é o que valida os dois limiares de uma vez.
    """
    from services.nivel_tecnologico import (
        PRODUTIVIDADE_MEDIA_BR, PRODUTIVIDADE_INTENSIVO)
    assert (float(PRODUTIVIDADE_MEDIA_BR)
            < EXAGRO_PRODUCAO_MEDIANA_ARROBA_HA
            < float(PRODUTIVIDADE_INTENSIVO))


def test_os_valores_de_2013_nao_viram_referencia_de_custo():
    """
    Guarda contra um erro que seria fácil e silencioso: usar o custo por
    cabeça do EXAGRO (R$ 299/ano, mediana de 2013) como referência para os
    nossos perfis, que são de 2023 e da safra 24/25.

    Uma década de inflação separa os dois. O EXAGRO entra pelo que compara
    entre SI — dispersão, sinal e ordem entre estados, que são adimensionais.
    """
    # Se alguém importar EXAGRO_RESULTADO_2013 dentro de custos_desembolso,
    # este teste falha e obriga a discussão sobre deflacionar.
    import services.custos_desembolso as cd
    assert 'EXAGRO' not in open(cd.__file__).read(), (
        'o EXAGRO 2013 entrou no módulo de custos — valores nominais de 2013 '
        'não se comparam com a safra 24/25 sem deflacionar'
    )
