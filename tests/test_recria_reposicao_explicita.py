"""A recria comprava o lote de volta todo ano, sem ninguém ter pedido.

Os dois motores de recria faziam `compras = animais_sai`: cada animal que sai
é reposto por compra, sempre, em todos os anos. A hipótese veio de uma ficha
real de 700 cabeças que documentava reposição 1:1 — mas virou lei do motor em
vez de premissa do caso.

A ficha não comprova reposição nenhuma. Ela é uma foto do estoque: não diz se
o produtor vai recomprar o lote, se vai reduzir a escala, ou se os animais
vêm da própria cria. E a hipótese não é neutra no crédito — a reposição
integral é precificada como desembolso, e num caso de 753 cabeças isso pesava
R$ 215.942 no ano 1, o bastante para inverter o sinal do resultado.

O default continua 100%: é o que os motores já faziam e o que a ficha de
referência documentava. O que muda é poder dizer outra coisa.
"""
import pytest

from ml_engine import simular_cenario
from services.engine.contracts import HerdState
from services.production_engine.recria import project_recria

RECRIA = [80, 90, 60, 70, 100, 160, 40, 120, 30, 20]


def _params(**extra):
    base = {
        'mort_pct': 3.0, 'preco_arroba': 320.0,
        'peso_entrada_arr': 6.5, 'peso_saida_arr': 13.5,
        'meses_recria': 12.0, 'custo_arroba': 57.0,
    }
    base.update(extra)
    return base


# ── production_engine ───────────────────────────────────────────────────────
def test_default_mantem_a_reposicao_integral():
    """Nada que já chamava o motor muda de resultado."""
    r = project_recria(HerdState(values=RECRIA, source="MANUAL", farm_id=None, metadata={}), _params(), years=3)
    a1 = r['anos'][0]

    assert a1['compras'] == a1['vendidos']
    assert a1['custo_reposicao'] > 0


def test_sem_reposicao_nao_compra_nem_paga():
    r = project_recria(HerdState(values=RECRIA, source="MANUAL", farm_id=None, metadata={}), _params(reposicao_pct=0), years=3)
    a1 = r['anos'][0]

    assert a1['compras'] == 0
    assert a1['custo_reposicao'] == 0
    assert a1['custo'] == a1['custo_manutencao']


def test_sem_reposicao_o_rebanho_encolhe():
    """É o ponto: sem recompra a escala cai, e o fluxo tem de mostrar isso."""
    com = project_recria(HerdState(values=RECRIA, source="MANUAL", farm_id=None, metadata={}), _params(), years=3)
    sem = project_recria(HerdState(values=RECRIA, source="MANUAL", farm_id=None, metadata={}), _params(reposicao_pct=0), years=3)

    assert sem['anos'][0]['total'] < com['anos'][0]['total']
    assert sem['anos'][2]['vendidos'] < com['anos'][2]['vendidos']


def test_reposicao_parcial_fica_entre_as_duas_pontas():
    zero = project_recria(HerdState(values=RECRIA, source="MANUAL", farm_id=None, metadata={}), _params(reposicao_pct=0), years=2)
    meio = project_recria(HerdState(values=RECRIA, source="MANUAL", farm_id=None, metadata={}), _params(reposicao_pct=50), years=2)
    cheio = project_recria(HerdState(values=RECRIA, source="MANUAL", farm_id=None, metadata={}), _params(reposicao_pct=100), years=2)

    a_zero, a_meio, a_cheio = (r['anos'][0] for r in (zero, meio, cheio))
    assert a_zero['compras'] < a_meio['compras'] < a_cheio['compras']
    assert a_meio['compras'] == pytest.approx(a_cheio['compras'] / 2, abs=1)


def test_a_premissa_usada_aparece_na_projecao():
    """O parecer precisa poder dizer de onde veio o número."""
    r = project_recria(HerdState(values=RECRIA, source="MANUAL", farm_id=None, metadata={}), _params(reposicao_pct=40), years=1)

    assert r['anos'][0]['reposicao_pct'] == 40.0


def test_percentual_fora_da_faixa_e_limitado():
    alto = project_recria(HerdState(values=RECRIA, source="MANUAL", farm_id=None, metadata={}), _params(reposicao_pct=500), years=1)
    baixo = project_recria(HerdState(values=RECRIA, source="MANUAL", farm_id=None, metadata={}), _params(reposicao_pct=-20), years=1)

    assert alto['anos'][0]['reposicao_pct'] == 100.0
    assert baixo['anos'][0]['reposicao_pct'] == 0.0


# ── ml_engine (o motor que o analista vê em /api/classificar) ───────────────
def test_o_motor_do_parecer_recebe_a_mesma_premissa():
    com = simular_cenario(RECRIA, 'conservador', ciclo='RECRIA',
                          preco_arroba=320, custo_arroba=57)
    sem = simular_cenario(RECRIA, 'conservador', ciclo='RECRIA',
                          preco_arroba=320, custo_arroba=57, reposicao_pct=0)

    assert com['anos'][0]['compras'] > 0
    assert sem['anos'][0]['compras'] == 0
    assert sem['anos'][0]['custo'] < com['anos'][0]['custo']


def test_o_default_do_motor_do_parecer_nao_mudou():
    antes = simular_cenario(RECRIA, 'conservador', ciclo='RECRIA',
                            preco_arroba=320, custo_arroba=57)
    explicito = simular_cenario(RECRIA, 'conservador', ciclo='RECRIA',
                                preco_arroba=320, custo_arroba=57,
                                reposicao_pct=100)

    assert antes['anos'][0]['compras'] == explicito['anos'][0]['compras']
    assert antes['anos'][0]['custo'] == explicito['anos'][0]['custo']


# ── A rota ──────────────────────────────────────────────────────────────────
def test_a_rota_aceita_a_premissa_do_analista():
    """Sem passar nada, o parecer sai como antes; passando 0, o custo cai."""
    import database as db
    from app import app

    db.init_db()
    email = 'reposrecria@example.com'
    u = db.buscar_usuario_email(email)
    if not u:
        db.criar_usuario(email, 'Repos', 'senha123')
        u = db.buscar_usuario_email(email)
    app.config['TESTING'] = True
    cli = app.test_client()
    with cli.session_transaction() as s:
        s['_user_id'] = str(u['id'])

    base = {'valores': RECRIA, 'preco': 320, 'custo_arroba': 57}
    padrao = cli.post('/api/classificar', json=base).get_json()
    sem = cli.post('/api/classificar',
                   json={**base, 'reposicao_recria_pct': 0}).get_json()

    a_padrao = padrao['projecao_anos'][0]
    a_sem = sem['projecao_anos'][0]
    assert a_sem['custo'] < a_padrao['custo'], (
        f"custo {a_sem['custo']} contra {a_padrao['custo']} — a premissa do "
        f'analista não chegou ao motor'
    )
    assert a_sem['resultado'] > a_padrao['resultado']


# ── A tela ──────────────────────────────────────────────────────────────────
def test_a_tela_expoe_a_premissa_e_a_envia():
    """De nada adianta o motor aceitar se o analista não consegue informar."""
    from pathlib import Path

    html = (Path(__file__).parents[1] / 'templates' / 'index.html').read_text(
        encoding='utf-8')

    assert 'id="c-repos-recria"' in html, 'campo ausente na tela'
    assert 'body.reposicao_recria_pct=parseFloat(reposV)' in html, (
        'o campo existe mas não entra no payload de /api/classificar')
    # Fica sob um rótulo que o separa do que a ficha comprova — a distinção
    # entre informado e estimado é o ponto da mudança.
    assert 'Premissas da projeção' in html
