"""
A base reprodutiva é quem já pariu.

O motor somava a faixa de 25–36 meses às matrizes (`va[6] + va[8]`) e projetava
bezerro em cima dela. O próprio ml_engine já afirmava o contrário desde julho,
na guarda de classificação, com a fonte:

    "a fêmea da faixa de 25–36m ainda NÃO PARIU — contá-la como matriz projeta
     bezerro que ainda não existe"

Embrapa Gado de Corte: idade média à primeira parição de 36,3 meses em 468
matrizes Nelore. Pantanal extensivo (CT 126): 40,0 meses.

Medido numa cria de 1.775 cabeças, antes da correção:

    base reprodutiva ..... 750 contra 600 reais
    nascidos por ano ..... 525 contra 420
    105 bezerros por ano que a fazenda não produz

É o mesmo defeito que a checagem de consistência tinha na superfície — a mesma
fêmea contada como plantel a repor E como reposição — uma camada abaixo.
"""
import pytest

import database as db
from app import app
from ml_engine import simular_cenario, calcular_ano

CRIA           = [300, 280, 200, 80, 100, 40, 150, 10, 600, 15]
CICLO_COMPLETO = [120, 100, 80, 70, 40, 50, 150, 80, 270, 40]


@pytest.fixture(scope='module')
def cli():
    db.init_db()
    email = 'basereprod@example.com'
    u = db.buscar_usuario_email(email)
    if not u:
        db.criar_usuario(email, 'Base', 'senha123')
        u = db.buscar_usuario_email(email)
    app.config['TESTING'] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u['id'])
    return c


# ── Quem pare ───────────────────────────────────────────────────────────────
def test_a_faixa_25_36m_nao_produz_bezerro():
    """
    O número que motivou tudo: os nascidos têm de sair de v[8], não de
    v[6]+v[8]. Com natalidade de 70% e 600 matrizes reais, são ~420 bezerros —
    não os ~525 que a soma antiga projetava.
    """
    r = simular_cenario(CRIA, 'conservador', ciclo='CRIA',
                        preco_arroba=330, custo_arroba=57)
    nascidos_ano1 = r['anos'][0]['bezerros']
    teto_real = CRIA[8] * 0.70
    teto_antigo = (CRIA[6] + CRIA[8]) * 0.70
    assert nascidos_ano1 <= teto_real * 1.02, (
        f'{nascidos_ano1} bezerros para {CRIA[8]} matrizes — a faixa de '
        f'25–36m voltou para a base reprodutiva'
    )
    assert nascidos_ano1 < teto_antigo * 0.85


def test_a_coorte_nao_some_do_rebanho():
    """
    Ela muda de PAPEL, não de existência: sai do lado que produz e entra no
    lado que ainda vai produzir. Se sumisse, o balanço perderia 150 cabeças.
    """
    r = simular_cenario(CRIA, 'conservador', ciclo='CRIA',
                        preco_arroba=330, custo_arroba=57)
    a1 = r['anos'][0]
    # Ela é promovida no ano 1: o plantel sobe da base declarada (600) para
    # 600 + 150 − baixas, e não fica em 600.
    assert a1['matrizes'] > CRIA[8], (
        f"{a1['matrizes']} matrizes contra base declarada de {CRIA[8]} — a "
        f"coorte de 25–36m deixou de amadurecer"
    )
    assert a1['matrizes'] <= CRIA[6] + CRIA[8]


def test_a_coorte_nao_e_liquidada_como_excedente():
    """
    Primeira tentativa desta correção jogava a faixa de 25–36m na regra de
    manutenção junto com as novilhas de 13–24m. Com 150 fêmeas e só 78 baixas
    a repor, a regra promovia 78 e mandava 172 para a VENDA: o ano 1 saltava
    de 785 para 955 cabeças vendidas e o resultado subia 46%.

    Era a ilusão do ano 1 de novo, agora liquidando a fêmea prestes a parir.
    Cruzar os 36 meses é calendário, não decisão de manejo.
    """
    r = simular_cenario(CRIA, 'conservador', ciclo='CRIA',
                        preco_arroba=330, custo_arroba=57)
    a1 = r['anos'][0]
    promovidas = a1['aumento_matrizes'] + a1['matrizes_descartadas']
    assert promovidas >= CRIA[6], (
        f'promovidas {promovidas} para uma coorte de {CRIA[6]} de 25–36m — '
        f'parte dela voltou a ser vendida como excedente'
    )


def test_a_coorte_paga_pasto():
    """
    Ela saiu da base reprodutiva e por um momento saiu do CUSTO junto —
    pastava de graça no modelo. O teste de custo por arroba pegou.

    Come como novilha adulta: peso de fêmea jovem, não de matriz, porque ainda
    não pariu nem amamenta.
    """
    sem_coorte = list(CRIA)
    sem_coorte[6] = 0
    com = simular_cenario(CRIA, 'conservador', ciclo='CRIA',
                          preco_arroba=330, custo_arroba=57)
    sem = simular_cenario(sem_coorte, 'conservador', ciclo='CRIA',
                          preco_arroba=330, custo_arroba=57)
    assert com['anos'][0]['custo'] > sem['anos'][0]['custo'], (
        '150 cabeças a mais não custaram nada'
    )


# ── O ciclo completo recebe a mesma regra ───────────────────────────────────
def test_o_ciclo_completo_usa_a_mesma_base():
    """
    A correção nasceu em `_simular_cria` e o ciclo completo tem motor próprio
    (`calcular_ano`), que ficou para trás na primeira passada — o DSCR não se
    mexeu e foi assim que percebi.
    """
    r = simular_cenario(CICLO_COMPLETO, 'conservador', ciclo='CICLO_COMPLETO',
                        preco_arroba=330, custo_arroba=57)
    nascidos = r['anos'][0]['bezerros']
    assert nascidos <= CICLO_COMPLETO[8] * 0.75 * 1.02, (
        f'{nascidos} bezerros para {CICLO_COMPLETO[8]} matrizes'
    )


def test_a_coorte_do_ciclo_completo_entra_no_plantel():
    r = simular_cenario(CICLO_COMPLETO, 'conservador', ciclo='CICLO_COMPLETO',
                        preco_arroba=330, custo_arroba=57)
    assert r['anos'][0]['matrizes'] > CICLO_COMPLETO[8]


def test_calcular_ano_sem_coorte_e_o_comportamento_de_antes():
    """`prestes_matrizes` é opcional e default 0 — nada que já chamava mudou."""
    comum = dict(matrizes=270, c0_femeas=120, c1_femeas=120,
                 c0_machos=110, c1_machos=110, bois=120,
                 nat_pct=0.70, desc_mat_pct=0.10, prop_boi=30, renov_boi_pct=0.20,
                 venda_bez_pct=0.75, mort_pct=0.03, preco_arroba=330,
                 custo_arroba=57)
    a = calcular_ano(**comum)
    b = calcular_ano(**comum, prestes_matrizes=0.0)
    assert a['matrizes_prox'] == b['matrizes_prox']
    # A coorte prestes agora sofre mortalidade normal antes de ser promovida
    # (ver calcular_ano) — não entra mais intacta como antes.
    c = calcular_ano(**comum, prestes_matrizes=150.0)
    assert c['matrizes_prox'] > b['matrizes_prox']
    assert c['matrizes_prox'] < b['matrizes_prox'] + 150


# ── A direção do erro corrigido ─────────────────────────────────────────────
def test_a_correcao_empurra_para_reprovar(cli):
    """
    Nascer menos bezerro é gerar menos caixa. A correção move o parecer para o
    lado de NEGAR, que é o barato num produto de crédito — e aqui é também o
    lado certo, porque os bezerros a mais não existiam.

    Medido no ciclo completo: DSCR mínimo caiu de 0,67 para 0,13.
    """
    r = cli.post('/api/classificar', json={
        'valores': CICLO_COMPLETO, 'preco': 330,
        'credito_valor': sum(CICLO_COMPLETO) * 1200,
        'prazo_meses': 36, 'juros_aa': 0.125}).get_json()
    dscr = r['parecer']['conclusao']['dscr_minimo']
    assert dscr < 0.40, (
        f'DSCR {dscr} — se voltou ao patamar de 0,67, a faixa de 25–36m '
        f'voltou para a base reprodutiva do ciclo completo'
    )
