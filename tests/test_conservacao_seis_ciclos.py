"""
Conservação de animais nas SEIS modalidades, com composições que expõem fugas.

`test_conservacao_rebanho.py` já cobria quatro ciclos, mas com rebanhos
equilibrados — e rebanho equilibrado esconde fuga. Estes casos usam
composições extremas de propósito, e foi assim que apareceram três vazamentos
que passavam despercebidos:

1. O motor de engorda montava dois baldes (`outros_f`, `outros_m`) e deixava
   `va[8]` — fêmeas acima de 36 meses — de FORA dos dois. Numa ficha de
   recria/engorda com 60 matrizes, o fechamento perdia exatamente essas 60
   cabeças, e a variação de estoque registrava uma perda patrimonial que nunca
   aconteceu.

2. O motor de cria contabilizava a mortalidade das matrizes em `mortes`, mas
   `matrizes_prox` não a descontava — as matrizes mortas seguiam no plantel e
   o ano fechava com mais animais do que entrou.

3. O motor de recria vendia a coorte 5–25m inteira todo ano e nunca vendia
   nada fora dela (ver test_ficha_recria_real.py).

O invariante é sempre o mesmo: fim = início + nascimentos + compras − vendas
− mortes.
"""
import pytest

from ml_engine import simular_cenario, carregar_modelo


@pytest.fixture(scope='module', autouse=True)
def _modelo():
    carregar_modelo()


# Composições deliberadamente desequilibradas, uma por modalidade.
REBANHOS = {
    'CRIA':           [45, 45, 45, 45, 40, 40, 90, 10, 330, 10],
    'RECRIA':         [11, 110, 11, 109, 105, 234, 45, 16, 59, 0],
    'ENGORDA':        [0, 0, 0, 0, 10, 585, 10, 70, 15, 10],
    'CICLO_COMPLETO': [40, 40, 40, 40, 50, 50, 80, 35, 275, 50],
    'RECRIA_ENGORDA': [0, 20, 10, 90, 60, 280, 40, 120, 60, 20],
    'CRIA_RECRIA':    [45, 45, 45, 45, 70, 90, 90, 20, 240, 10],
}


def _ano1(ciclo, v):
    return simular_cenario(v, 'conservador', ciclo=ciclo,
                           preco_arroba=320, custo_arroba=119)['anos'][0]


@pytest.mark.parametrize('ciclo', list(REBANHOS))
def test_balanco_de_animais_fecha(ciclo):
    v = REBANHOS[ciclo]
    a = _ano1(ciclo, v)

    inicio  = sum(v)
    nasc    = a.get('bezerros', 0)
    compras = a.get('compras', 0)
    # `vendidos` já inclui o descarte de matrizes no CICLO_COMPLETO (a média
    # ponderada de peso em ml_engine.py exige isso do denominador) — somar de
    # novo aqui dobraria a contagem. Nos demais ciclos `vendidos` exclui o
    # descarte e precisa da soma. Ver test_conservacao_rebanho.py.
    descarte_ja_incluido = ciclo == 'CICLO_COMPLETO'
    vendas = a.get('vendidos', 0) + (0 if descarte_ja_incluido else a.get('matrizes_descartadas', 0))
    mortes  = a.get('mortes', 0)
    esperado = inicio + nasc + compras - vendas - mortes

    tolerancia = max(3, inicio * 0.02)
    assert abs(a['total'] - esperado) <= tolerancia, (
        f'{ciclo}: fim={a["total"]}, mas início({inicio}) + nasc({nasc}) '
        f'+ compras({compras}) − vendas({vendas}) − mortes({mortes}) = {esperado}. '
        f'{a["total"] - esperado} animais não contabilizados.'
    )


@pytest.mark.parametrize('ciclo', list(REBANHOS))
def test_fechamento_soma_o_total(ciclo):
    """
    O fluxo GEP valora o fechamento por matrizes + bois_fim + jovens_f/m
    (+ prestes_matrizes_fim, só no CICLO_COMPLETO — fêmeas de 25–36m que
    ainda não pariram, coorte própria desde a correção por coortes reais). Se
    essas chaves não somarem `total`, a variação de estoque acusa perda de
    animais que continuam no plantel.
    """
    a = _ano1(ciclo, REBANHOS[ciclo])
    soma = (a.get('matrizes', 0) + a.get('bois_fim', 0)
            + a.get('jovens_f_fim', 0) + a.get('jovens_m_fim', 0)
            + a.get('prestes_matrizes_fim', 0))
    assert abs(soma - a['total']) <= max(3, a['total'] * 0.02), (
        f'{ciclo}: categorias somam {soma} mas total={a["total"]}'
    )


@pytest.mark.parametrize('ciclo', list(REBANHOS))
def test_ninguem_vende_mais_do_que_tem(ciclo):
    """
    A engorda chegou a projetar a venda de 584 cabeças que não existiam. Vendas
    só podem sair do plantel de abertura mais o que nasceu ou foi comprado.
    """
    v = REBANHOS[ciclo]
    a = _ano1(ciclo, v)
    disponivel = sum(v) + a.get('bezerros', 0) + a.get('compras', 0)
    vendas = a.get('vendidos', 0) + a.get('matrizes_descartadas', 0)
    assert vendas <= disponivel, (
        f'{ciclo}: vendeu {vendas} com {disponivel} disponíveis'
    )


def test_femeas_adultas_nao_somem_na_engorda():
    """
    Regressão do vazamento 1: `va[8]` fora dos dois baldes. Um rebanho de
    engorda com muitas fêmeas adultas perdia todas elas no fechamento.
    """
    sem_femeas  = [0, 0, 0, 0, 0, 100, 0, 300, 0, 100]
    com_femeas  = [0, 0, 0, 0, 0, 100, 0, 300, 200, 100]   # +200 em va[8]

    a_sem = _ano1('ENGORDA', sem_femeas)
    a_com = _ano1('ENGORDA', com_femeas)

    assert a_com['total'] - a_sem['total'] == pytest.approx(200, abs=10), (
        f'declarar 200 fêmeas adultas a mais só aumentou o fechamento em '
        f'{a_com["total"] - a_sem["total"]} — elas estão sumindo do modelo'
    )


def test_matrizes_mortas_saem_do_plantel_na_cria():
    """
    Regressão do vazamento 2: a mortalidade das matrizes era contabilizada em
    `mortes` mas não descontada do fechamento.
    """
    v = [0, 0, 0, 0, 0, 0, 0, 0, 500, 10]   # rebanho quase só de matrizes
    a = _ano1('CRIA', v)
    esperado = (sum(v) + a.get('bezerros', 0) + a.get('compras', 0)
                - a.get('vendidos', 0) - a.get('matrizes_descartadas', 0)
                - a.get('mortes', 0))
    assert abs(a['total'] - esperado) <= max(3, sum(v) * 0.02), (
        f'fim={a["total"]}, esperado={esperado} — matrizes mortas seguem no plantel'
    )
