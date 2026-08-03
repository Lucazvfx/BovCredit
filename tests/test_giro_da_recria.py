"""
A recria tinha um teto estrutural de 46% de desfrute, e o painel mede 79,68%.

A reposição entrava toda em 0–12m (`n0_f, n0_m = 0.0, compras`). Isso fazia o
animal atravessar DUAS faixas etárias antes de sair, num ciclo que
`meses_recria` declara ser de 12 meses. Em regime permanente, com N entrando
por ano:

    0–12m ..... N
    13–24m .... N       → vende 0,83N, sobra 0,17N
    25–36m .... 0,17N   → vende tudo
    rebanho = 2,17N,  vendas = N,  desfrute = 1/2,17 = 46%

Nenhuma calibração de parâmetro passa de 46%. O modelo não estava mal
ajustado — estava mal construído: faixa etária não é tempo de casa, e um
desmamado comprado aos 8 meses e vendido aos 20 fica 12 meses na fazenda, não
24.

Junto vinha um segundo defeito: toda a reposição era MACHO, então a linha de
fêmeas se extinguia na terceira safra.

O efeito conjunto era um pingue-pongue de dois anos — desfrute alternando
29%/63% e o resultado trocando de sinal junto. Como a recomendação segue o ano
crítico, ela pegava sempre o ano ruim: toda recria saía negativa.
"""
import pytest

from ml_engine import simular_cenario
from services.benchmarks_nacionais import DESFRUTE_MODALIDADE, PAINEIS_DESFRUTE_2022

# Ficha real de recria, 700 cabeças, usada em test_ficha_recria_real.
FICHA_REAL = [11, 110, 11, 109, 105, 234, 45, 16, 59, 0]
SINTETICA  = [40, 40, 120, 140, 60, 200, 20, 180, 10, 30]

PAINEL_RECRIA = next(p[3] for p in PAINEIS_DESFRUTE_2022 if p[2] == 'RECRIA')


def _anos(v, n=8):
    r = simular_cenario(v, 'conservador', ciclo='RECRIA',
                        preco_arroba=330, custo_arroba=57, anos=n)
    return r['anos']


def _desfrute(a):
    return a['vendidos'] / max(a['total'], 1) * 100


# ── O teto estrutural caiu ──────────────────────────────────────────────────
def test_o_regime_alcanca_a_faixa_de_referencia():
    """
    O teste que define a correção. Antes, o desfrute de regime não passava de
    46% por construção, contra uma faixa de referência de 60–95%.
    """
    lo, hi = DESFRUTE_MODALIDADE['RECRIA']
    regime = [_desfrute(a) for a in _anos(SINTETICA)[2:]]
    assert min(regime) >= lo, (
        f'desfrute de regime {min(regime):.1f}% abaixo do piso {lo:.0f}% — '
        f'o teto estrutural de 46% voltou'
    )
    assert max(regime) <= hi


def test_o_regime_cerca_o_painel_medido():
    """Pontes e Lacerda/MT mede 79,68%. O regime tem de cercar esse número."""
    regime = [_desfrute(a) for a in _anos(SINTETICA)[2:]]
    assert min(regime) < PAINEL_RECRIA < max(regime), (
        f'regime {min(regime):.1f}–{max(regime):.1f}% contra painel '
        f'{PAINEL_RECRIA}%'
    )


def test_o_resultado_para_de_trocar_de_sinal():
    """
    O pingue-pongue era o que reprovava toda recria: a recomendação segue o ano
    crítico, e o ano crítico era sempre o ruim da oscilação.
    """
    resultados = [a['resultado'] for a in _anos(SINTETICA)[1:]]
    assert all(r > 0 for r in resultados), (
        f'anos de regime com resultado negativo: '
        f'{[r for r in resultados if r <= 0]}'
    )


# ── A linha de fêmeas não se extingue ───────────────────────────────────────
def test_a_reposicao_repoe_femea_tambem():
    """
    Era `n0_f, n0_m = 0.0, compras`: vendia-se fêmea de 25–36m e repunha só
    macho. Da terceira safra em diante o rebanho não tinha mais fêmea nenhuma,
    e reposição 1:1 é um animal por animal do MESMO tipo.
    """
    anos = _anos(SINTETICA)
    assert all(a['femeas_vendidas'] > 0 for a in anos[2:]), (
        'a linha de fêmeas se extinguiu — a reposição voltou a ser só macho'
    )


def test_a_reposicao_continua_um_para_um():
    """A correção mexeu em ONDE a reposição entra, não em QUANTO se repõe."""
    for a in _anos(SINTETICA):
        assert a['compras'] == pytest.approx(a['vendidos'], rel=0.02), a


# ── A ficha real reconcilia com o painel ────────────────────────────────────
def test_a_ficha_real_e_o_painel_deixam_de_brigar():
    """
    Duas fontes que pareciam se contradizer: a ficha real de 700 cabeças
    declara desfrute de 45%, e o painel de Pontes e Lacerda mede 79,68%.

    Não brigam — descrevem momentos diferentes. Os 45% são o PRIMEIRO ano de um
    rebanho com 241 animais de 0–12m em "permanência / evolução", que ainda não
    vendem. Quando eles amadurecem, a mesma fazenda roda a ~73%.

    O modelo agora reproduz os dois: 44,9% no ano 1 e 72–75% em regime.
    """
    anos = _anos(FICHA_REAL)
    assert _desfrute(anos[0]) == pytest.approx(45.0, abs=2.0), (
        f'ano 1 {_desfrute(anos[0]):.1f}% — a ficha declara 45,0%'
    )
    regime = [_desfrute(a) for a in anos[2:]]
    assert 60.0 <= min(regime), f'regime caiu para {min(regime):.1f}%'
    assert abs(sum(regime) / len(regime) - PAINEL_RECRIA) < 12.0, (
        f'regime médio {sum(regime)/len(regime):.1f}% longe do painel '
        f'{PAINEL_RECRIA}%'
    )


def test_o_ano_1_da_ficha_real_nao_se_mexeu():
    """
    A correção é do ROLAMENTO das coortes, não do ano 1 — que vende o estoque
    declarado. Se o ano 1 mudou, a correção vazou para onde a ficha real já
    ancorava o modelo.
    """
    a1 = _anos(FICHA_REAL)[0]
    assert a1['vendidos'] == pytest.approx(315, rel=0.05)
    assert a1['machos_vendidos'] == pytest.approx(211, rel=0.05)
    assert a1['femeas_vendidas'] == pytest.approx(104, rel=0.05)
