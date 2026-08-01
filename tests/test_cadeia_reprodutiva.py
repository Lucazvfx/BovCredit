"""
A cadeia reprodutiva desconta cada perda UMA vez.

Vieira et al. (2005), Embrapa Gado de Corte, mede prenhez, natalidade, desmama
e mortalidade de bezerro no MESMO rebanho por quatro safras. É o que permite
provar a identidade em vez de supô-la:

    taxa de desmama = natalidade × (1 − mortalidade de bezerro)

O motor calculava `nascidos × desmama × (1 − mort_bez)`, com desmama default de
82%. Isso descontava a mesma perda três vezes e projetava 53,4 bezerros
desmamados por 100 matrizes — abaixo dos 58,0 do Pantanal extensivo, que é o
sistema mais pobre que já medimos, e 31% abaixo dos 77,2 do próprio Vieira.

Numa cria, bezerro é a receita inteira.
"""
import pytest

from ml_engine import simular_cenario
from services.parametros_zootecnicos import (
    taxa_desmama_efetiva, natalidade_de_prenhez,
    APROVEITAMENTO_PRENHEZ_PCT, NATALIDADE_MATRIZES_EXTENSIVO_PCT,
    MORTALIDADE_PRE_DESMAMA_MEDIDA_PCT,
)

# (safra, prenhez, natalidade, desmama, mortalidade de bezerro)
VIEIRA_2005 = [
    ('1996/97', 88.2, 84.0, 82.4, 2.00),
    ('1997/98', 90.8, 87.5, 80.8, 8.00),
    ('1998/99', 91.4, 87.1, 82.8, 5.00),
    ('1999/00', 79.7, 68.1, 62.8, 8.00),
    ('média',   87.5, 81.7, 77.2, 6.00),
]

CRIA = [300, 280, 200, 80, 100, 40, 150, 10, 600, 15]


# ── A identidade, contra o dado ─────────────────────────────────────────────
@pytest.mark.parametrize('safra,prenhez,nat,desm,mort', VIEIRA_2005,
                         ids=[r[0] for r in VIEIRA_2005])
def test_a_identidade_fecha_nas_quatro_safras(safra, prenhez, nat, desm, mort):
    """
    Se a identidade não fechasse, a correção seria chute. Ela fecha com erro de
    até 0,4 ponto percentual em todas as safras — inclusive na safra ruim de
    1999/00, onde os três índices caem juntos.

    A folga de 0,5 ponto é a precisão com que a fonte publica os números
    (uma casa decimal em três taxas independentes), não margem de manobra.
    """
    previsto = taxa_desmama_efetiva(natalidade_pct=nat,
                                    mortalidade_bezerro_pct=mort) * 100
    assert previsto == pytest.approx(desm, abs=0.5), (
        f'{safra}: natalidade {nat}% × (1−{mort}%) = {previsto:.1f}%, '
        f'mas a fonte publica desmama de {desm}%'
    )


def test_a_desmama_declarada_vence_a_derivacao():
    """
    Declaração do analista é medição daquela fazenda e já engloba a cadeia
    inteira por definição. Ela não pode ser multiplicada por mais nada.
    """
    assert taxa_desmama_efetiva(70.0, 7.0, desmama_declarada_pct=64.0) == 0.64
    # Sem declaração, deriva.
    assert taxa_desmama_efetiva(70.0, 7.0) == pytest.approx(0.651, abs=0.001)


def test_a_prenhez_declarada_vira_natalidade():
    """
    O campo de prenhez da ficha era decorativo: aparecia na tela, era comparado
    com cinco fontes no painel nacional, e não entrava em cálculo nenhum. A
    perda gestacional medida (6,6%) é o que faltava para ligá-lo.
    """
    assert natalidade_de_prenhez(87.5) == pytest.approx(81.7, abs=0.3)
    assert float(APROVEITAMENTO_PRENHEZ_PCT) < 100, (
        'a perda gestacional virou ganho — natalidade não pode superar prenhez'
    )


# ── O efeito no motor ───────────────────────────────────────────────────────
def test_a_cria_produz_mais_bezerro_que_o_pantanal_extensivo():
    """
    O teto de sanidade da correção. Com natalidade de 70% projetada, a cria não
    pode desmamar MENOS que uma fazenda extensiva modal do Pantanal, que opera
    a 0,30 UA/ha em planície alagável com natalidade medida de 62,39%.

    Antes: 53,4 por 100 matrizes, contra 58,0 do Pantanal. A projeção
    "conservadora" era pior que o pior sistema medido.
    """
    nosso = taxa_desmama_efetiva(70.0, 7.0) * 100
    pantanal = (float(NATALIDADE_MATRIZES_EXTENSIVO_PCT)
                * (1 - float(MORTALIDADE_PRE_DESMAMA_MEDIDA_PCT) / 100))
    assert nosso > pantanal, (
        f'projetamos {nosso:.1f} desmamados/100 matrizes contra {pantanal:.1f} '
        f'medidos num extensivo de planície alagável'
    )


def test_o_ano_1_nao_se_mexe_e_os_anos_de_regime_sim():
    """
    O ano 1 comercializa o ESTOQUE DECLARADO na ficha — ele não depende da
    natalidade, e tem de ficar igual. Se ele se mexeu, a correção vazou para
    onde não devia.

    Os anos de regime vendem a produção corrente, e é lá que os 22% a mais de
    bezerro (1 ÷ 0,82, o fator que sobrava) têm de aparecer.
    """
    r = simular_cenario(CRIA, 'conservador', ciclo='CRIA',
                        preco_arroba=330, custo_arroba=57)
    anos = r['anos']
    assert anos[0]['vendidos'] == 785, (
        'o ano 1 mudou — ele vende estoque declarado e não deveria depender '
        'da cadeia reprodutiva'
    )
    assert anos[2]['vendidos'] > 370, (
        f"ano 3 vende {anos[2]['vendidos']} — antes da correção eram 316"
    )
    # O plantel para de derreter tão rápido.
    assert anos[4]['total'] > 1000
