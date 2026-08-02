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


@pytest.fixture(scope='module')
def cli():
    import database as db
    from app import app
    db.init_db()
    email = 'cadeia@example.com'
    u = db.buscar_usuario_email(email)
    if not u:
        db.criar_usuario(email, 'Cadeia', 'senha123')
        u = db.buscar_usuario_email(email)
    app.config['TESTING'] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u['id'])
    return c


def _resposta_rota(cli, valores):
    return cli.post('/api/classificar', json={
        'valores': valores, 'preco': 330,
        'credito_valor': sum(valores) * 1200,
        'prazo_meses': 36, 'juros_aa': 0.125}).get_json()


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

    O NÚMERO DO ANO 1 MUDOU DEPOIS, por outra correção: a faixa de 25–36m saiu
    da base reprodutiva e entrou na reposição. Com 150 fêmeas amadurecendo
    contra 78 baixas a repor, sobra excedente jovem para vender, e o ano 1
    passou de 785 para 885 cabeças.

    Isso NÃO desmente o que este teste prende. O ponto é que o ano 1 não
    depende da CADEIA REPRODUTIVA — ele vende estoque declarado. Prender o
    valor absoluto faria o teste brigar com toda correção futura de
    composição, então o que se prende é a propriedade: mexer na natalidade não
    move o ano 1.
    """
    r = simular_cenario(CRIA, 'conservador', ciclo='CRIA',
                        preco_arroba=330, custo_arroba=57)
    anos = r['anos']
    magro = simular_cenario(CRIA, 'conservador', ciclo='CRIA',
                            preco_arroba=330, custo_arroba=57, nat_pct=45)
    assert anos[0]['vendidos'] == magro['anos'][0]['vendidos'], (
        'o ano 1 passou a depender da natalidade — ele vende estoque '
        'declarado e não deveria'
    )
    assert anos[2]['vendidos'] > magro['anos'][2]['vendidos'], (
        'a natalidade parou de mover os anos de regime'
    )
    # O plantel para de derreter tão rápido.
    assert anos[4]['total'] > 900


# ── Reposição: requisito de manutenção, não alavanca de DSCR ────────────────
def test_o_descarte_de_manutencao_nao_virou_default():
    """
    Embrapa-CPATSA (1985) estima 15% de descarte anual como o necessário para
    MANTER o nível de produtividade, e o painel do Pantanal mede 14%. A
    tentação é subir o nosso default de 10% para lá.

    Medido, seria o pior conserto possível. Numa cria com 100 novilhas na
    ficha, descartar 15% sobe a receita do ano 3 de R$ 1.086.594 para
    R$ 1.200.033 e derrete o plantel de 629 para 510 matrizes — porque não há
    novilha para repor. É vender a matriz para pagar a parcela, e o DSCR
    melhora exatamente por isso.

    Os 15% são REQUISITO. Pressupõem que a reposição exista.
    """
    from ml_engine import PARAMS_POR_CICLO
    from services.parametros_zootecnicos import DESCARTE_MANUTENCAO_PCT
    assert PARAMS_POR_CICLO['CRIA']['desc_mat_pct'] < float(DESCARTE_MANUTENCAO_PCT)

    receita, matrizes = {}, {}
    for d in (10.0, 15.0):
        r = simular_cenario(CRIA, 'conservador', ciclo='CRIA',
                            preco_arroba=330, custo_arroba=57, desc_pct=d)
        receita[d] = r['anos'][2]['receita']
        matrizes[d] = r['anos'][4]['matrizes']
    assert receita[15.0] > receita[10.0], 'descartar mais deixou de subir a receita'
    assert matrizes[15.0] < matrizes[10.0], (
        'descartar mais parou de encolher o plantel — se a promoção mudou, '
        'a decisão de não subir o default precisa ser reavaliada'
    )


def test_o_aviso_de_reposicao_separa_ficha_com_e_sem_novilha():
    """
    O requisito vira informação onde ele não é alavanca: quantas novilhas a
    ficha tem contra quantas matrizes saem por ano.
    """
    from services.parametros_zootecnicos import (
        avaliar_reposicao, REPOSICAO_MINIMA_PCT)

    com = avaliar_reposicao(matrizes=750, novilhas=100, descarte_pct=10.0)
    assert com['suficiente'] and com['sustenta_manutencao']
    assert com['reposicao_sustentada_pct'] >= float(REPOSICAO_MINIMA_PCT)

    sem = avaliar_reposicao(matrizes=750, novilhas=10, descarte_pct=10.0)
    assert not sem['suficiente'] and not sem['sustenta_manutencao']

    # Sem matriz não há o que avaliar — recria e engorda não podem quebrar.
    assert avaliar_reposicao(matrizes=0, novilhas=0, descarte_pct=0.0) is None


def test_o_aviso_de_reposicao_chega_na_rota(cli):
    r = _resposta_rota(cli, CRIA)
    assert r['reposicao_plantel']['reposicao_sustentada_pct'] > 0
    magra = _resposta_rota(cli, [300, 280, 200, 80, 10, 40, 150, 10, 600, 15])
    assert magra['reposicao_plantel']['suficiente'] is False
