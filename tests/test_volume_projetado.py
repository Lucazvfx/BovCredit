"""
O analista passa a controlar o VOLUME, e a engorda para de girar quatro vezes.

Até aqui o analista podia sobrescrever tudo do lado do CUSTO — desembolso,
natalidade, mortalidade, desmama — e nada do lado do VOLUME. A taxa de venda de
bezerras e o descarte de matrizes vinham fixos de PARAMS_POR_CICLO e só eram
ajustáveis pela rota de cenários, que não emite parecer.

Quem lê a ficha sabe quantas bezerras aquela fazenda retém. A projeção não.

E a engorda tinha `dias_engorda = 90` fixo. Com entrada de 405 kg e saída de
520, isso implica ganho de 1,28 kg/dia — acima do 1,10 medido em
semiconfinamento — num perfil de custo que descreve pasto com suplementação.
Como `lotes_ano = int(365/dias)`, 90 dias davam QUATRO giros por ano:

    desfrute projetado 273%   contra faixa de referência de 80–120%
    DSCR 6,14

O erro corria a favor de APROVAR, que é o lado caro num produto de crédito.
"""
import pytest

import database as db
from app import app
from ml_engine import simular_cenario, PARAMS_POR_CICLO
from services.custos_desembolso import custo_arroba_padrao

CRIA    = [300, 280, 200, 80, 100, 40, 150, 10, 600, 15]
ENGORDA = [10, 8, 20, 18, 50, 80, 20, 120, 10, 400]


@pytest.fixture(scope='module')
def cli():
    db.init_db()
    email = 'volume@example.com'
    u = db.buscar_usuario_email(email)
    if not u:
        db.criar_usuario(email, 'Volume', 'senha123')
        u = db.buscar_usuario_email(email)
    app.config['TESTING'] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u['id'])
    return c


def _parecer(cli, valores, **extra):
    corpo = {'valores': valores, 'preco': 330,
             'credito_valor': sum(valores) * 1200,
             'prazo_meses': 36, 'juros_aa': 0.125}
    corpo.update(extra)
    return cli.post('/api/classificar', json=corpo).get_json()


# ── A taxa de venda passa a ser do analista ─────────────────────────────────
def test_a_taxa_de_venda_chega_na_projecao(cli):
    """Sem o campo, o parecer usa o padrão do ciclo; com ele, obedece."""
    padrao = _parecer(cli, CRIA)['parecer']['conclusao']['dscr_minimo']
    igual  = _parecer(cli, CRIA, venda_bez_pct=PARAMS_POR_CICLO['CRIA']['venda_bez_pct'])
    assert igual['parecer']['conclusao']['dscr_minimo'] == padrao

    menos = _parecer(cli, CRIA, venda_bez_pct=30)['parecer']['conclusao']['dscr_minimo']
    assert menos != padrao, 'o campo não chegou na simulação'


def test_reter_bezerra_reduz_o_caixa_do_ano(cli):
    """
    Contra-intuitivo e correto: reter bezerra é deixar de vender, e DSCR mede
    CAIXA. O rebanho retido vira valor de estoque, que não paga parcela.

    Registrado em teste porque a leitura natural é a oposta — "reter é bom para
    a fazenda, logo bom para o crédito" — e alguém vai tentar "consertar" isso.
    """
    vende_muito = _parecer(cli, CRIA, venda_bez_pct=75)['parecer']['conclusao']
    vende_pouco = _parecer(cli, CRIA, venda_bez_pct=15)['parecer']['conclusao']
    assert vende_pouco['dscr_minimo'] < vende_muito['dscr_minimo']


def test_a_taxa_de_venda_e_limitada_a_faixa_valida(cli):
    """Percentual fora de 0–100 é erro de digitação, não política."""
    for absurdo, equivale in ((150, 100), (-20, 0)):
        a = _parecer(cli, CRIA, venda_bez_pct=absurdo)['parecer']['conclusao']
        b = _parecer(cli, CRIA, venda_bez_pct=equivale)['parecer']['conclusao']
        assert a['dscr_minimo'] == b['dscr_minimo'], absurdo


def test_a_venda_nao_estabiliza_o_rebanho_de_cria():
    """
    O campo é útil, mas NÃO conserta a cria — e é importante que isso esteja
    escrito, para ninguém dar o problema por resolvido.

    Mesmo retendo 100% das bezerras, as matrizes caem de 750 para 526 em cinco
    anos. A causa é outra: `promovidas = nov_F × 0,20` enquanto o descarte é
    `matrizes × 0,10`. Com 750 matrizes isso descarta 75 e promove 20 — a base
    reprodutiva perde ~50 cabeças por ano, e a receita cai junto.
    """
    ca = custo_arroba_padrao('CRIA', 11.31)
    mat_ini = CRIA[6] + CRIA[8]
    for vb in (75, 0):
        r = simular_cenario(CRIA, cenario='conservador', ciclo='CRIA',
                            preco_arroba=330.0, custo_arroba=ca, venda_bez_pct=vb)
        assert r['anos'][4]['matrizes'] < mat_ini * 0.75, (
            f'venda {vb}%: a base reprodutiva parou de encolher — se isso passou '
            f'a ser verdade, a causa foi corrigida e este teste deve sair'
        )


# ── A engorda para de girar quatro vezes ────────────────────────────────────
def test_a_duracao_da_engorda_sai_do_ganho_de_peso():
    """
    115 kg de ganho a 0,85 kg/dia são 135 dias, e 135 dias são dois giros por
    ano — não quatro. A zootecnia passa a mandar na duração.
    """
    ca = custo_arroba_padrao('ENGORDA', 17.21)
    r = simular_cenario(ENGORDA, cenario='conservador', ciclo='ENGORDA',
                        preco_arroba=330.0, custo_arroba=ca)
    assert r['anos'][0]['lotes_por_ano'] == 2


def test_gmd_maior_encurta_o_ciclo_e_aumenta_os_giros():
    ca = custo_arroba_padrao('ENGORDA', 17.21)
    lotes = {}
    for gmd in (0.70, 0.85, 1.28):
        r = simular_cenario(ENGORDA, cenario='conservador', ciclo='ENGORDA',
                            preco_arroba=330.0, custo_arroba=ca,
                            ganho_peso_kg_dia=gmd)
        lotes[gmd] = r['anos'][0]['lotes_por_ano']
    assert lotes[0.70] <= lotes[0.85] < lotes[1.28]


def test_o_desfrute_da_engorda_deixou_de_ser_o_triplo_da_faixa():
    """
    Antes: 273% contra faixa de 80–120%, com DSCR 6,14. O erro corria a favor
    de aprovar — o lado caro num produto de crédito.
    """
    from services.benchmarks_nacionais import DESFRUTE_MODALIDADE
    _, teto = DESFRUTE_MODALIDADE['ENGORDA']
    ca = custo_arroba_padrao('ENGORDA', 17.21)
    r = simular_cenario(ENGORDA, cenario='conservador', ciclo='ENGORDA',
                        preco_arroba=330.0, custo_arroba=ca)
    desfrute = r['anos'][0]['vendidos'] / sum(ENGORDA) * 100
    assert desfrute < 273.0 * 0.6, f'{desfrute:.1f}% — a duração voltou a ser fixa'
    assert desfrute < teto * 1.25, f'{desfrute:.1f}% contra teto de {teto}%'


def test_gmd_absurdo_nao_produz_ciclo_impossivel():
    """Um GMD de zero ou negativo viraria divisão por zero e giro infinito."""
    ca = custo_arroba_padrao('ENGORDA', 17.21)
    for gmd in (0.0, -1.0, 0.01):
        r = simular_cenario(ENGORDA, cenario='conservador', ciclo='ENGORDA',
                            preco_arroba=330.0, custo_arroba=ca,
                            ganho_peso_kg_dia=gmd)
        assert r['anos'][0]['lotes_por_ano'] >= 1


def test_o_gmd_do_analista_chega_pela_rota(cli):
    a = _parecer(cli, ENGORDA)['parecer']['conclusao']['dscr_minimo']
    b = _parecer(cli, ENGORDA, ganho_peso_kg_dia=1.28)['parecer']['conclusao']['dscr_minimo']
    assert b > a, 'o GMD informado não chegou na projeção'
