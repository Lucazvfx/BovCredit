"""
O nível tecnológico deixa de mexer só no custo e passa a mexer na PRODUÇÃO.

Estava escrito em services/nivel_tecnologico.py como pendência declarada: um
extensivo colhe menos arroba por cabeça, a simulação projetava as mesmas nos
três níveis, e por isso o custo POR ARROBA do extensivo saía subestimado. A
correção exigia saber quanta arroba a menos um extensivo colhe.

O número chegou na Tabela 2.3 — GMD da desmama ao abate por manejo de
suplementação, que a fonte organiza justamente por idade de abate:

    32–36 meses   0,40–0,50 kg/dia   sem creep, mineral e pasto
    22–26 meses   0,60–0,70          creep opcional, terminação na 2ª seca
    17–18 meses   0,80–0,90          creep + suplemento múltiplo
    13–15 meses   1,20–1,30          creep + confinamento

O default de todo mundo era 0,85 — o valor do PRECOCE.
"""
import pytest

import database as db
from app import app
from services.nivel_tecnologico import (
    GMD_POR_NIVEL, GMD_PADRAO_SEM_NIVEL, gmd_do_nivel,
    EXTENSIVO, MEDIO, INTENSIVO, INDEFINIDO,
)

ENGORDA = [10, 10, 10, 20, 10, 120, 10, 180, 10, 400]


@pytest.fixture(scope='module')
def cli():
    db.init_db()
    email = 'nivelprod@example.com'
    u = db.buscar_usuario_email(email)
    if not u:
        db.criar_usuario(email, 'Nivel', 'senha123')
        u = db.buscar_usuario_email(email)
    app.config['TESTING'] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u['id'])
    return c


def _resposta(cli, valores, **extra):
    return cli.post('/api/classificar', json={
        'valores': valores, 'preco': 330,
        'credito_valor': sum(valores) * 1200,
        'prazo_meses': 36, 'juros_aa': 0.125, **extra}).get_json()


# ── A tabela ────────────────────────────────────────────────────────────────
def test_o_gmd_cresce_com_a_intensificacao():
    assert (float(GMD_POR_NIVEL[EXTENSIVO])
            < float(GMD_POR_NIVEL[MEDIO])
            < float(GMD_POR_NIVEL[INTENSIVO]))


@pytest.mark.parametrize('nivel,faixa', [
    (EXTENSIVO, (0.40, 0.50)),
    (MEDIO,     (0.60, 0.70)),
    (INTENSIVO, (0.80, 0.90)),
])
def test_cada_nivel_fica_dentro_da_faixa_da_fonte(nivel, faixa):
    """Prende o valor à Tabela 2.3, para ninguém 'ajustar' o número no olho."""
    lo, hi = faixa
    assert lo <= float(GMD_POR_NIVEL[nivel]) <= hi


def test_o_default_sem_nivel_deixou_de_supor_precoce():
    """
    Supor 0,85 de quem não declarou área é supor abate aos 17–18 meses com
    creep feeding — a suposição mais otimista da tabela, num produto em que
    otimismo vira arroba, que vira DSCR, que vira aprovação.

    O meio da escala é a posição honesta do desconhecido, e ainda fica
    otimista perto dos ~30+ meses da média brasileira.
    """
    assert GMD_PADRAO_SEM_NIVEL == float(GMD_POR_NIVEL[MEDIO])
    assert gmd_do_nivel(None) == GMD_PADRAO_SEM_NIVEL
    assert gmd_do_nivel(INDEFINIDO) == GMD_PADRAO_SEM_NIVEL


# ── O efeito atravessa a rota ───────────────────────────────────────────────
def test_a_area_declarada_muda_a_producao_projetada(cli):
    """
    O teste que a pendência pedia: mesma ficha, mesma modalidade, mesmo preço,
    só muda a área — e a arroba projetada muda junto, porque a área decide o
    nível e o nível decide o GMD.

    Antes desta mudança os três davam o mesmo número.
    """
    arrobas = {}
    for rot, area in [('extensivo', 3000), ('medio', 900), ('intensivo', 150)]:
        r = _resposta(cli, ENGORDA, area_pasto_ha=area)
        assert r['nivel_tecnologico']['nivel'] == rot
        arrobas[rot] = r['projecao_anos'][0]['arrobas_vendidas']

    assert arrobas['extensivo'] < arrobas['medio'] < arrobas['intensivo'], arrobas
    # E a diferença é de sistema, não de arredondamento.
    assert arrobas['intensivo'] > arrobas['extensivo'] * 1.5, arrobas


def test_o_gmd_do_analista_vence_o_nivel(cli):
    """
    Quem confina informa o GMD e vence o default. Confinamento não é um degrau
    de intensificação de pasto — é outro sistema, e o nosso perfil de custo de
    engorda descreve pasto com suplementação.
    """
    sem = _resposta(cli, ENGORDA, area_pasto_ha=3000)
    com = _resposta(cli, ENGORDA, area_pasto_ha=3000, ganho_peso_kg_dia=1.25)
    assert (com['projecao_anos'][0]['arrobas_vendidas']
            > sem['projecao_anos'][0]['arrobas_vendidas'] * 1.5)


def test_sem_area_o_parecer_nao_inventa_nivel(cli):
    r = _resposta(cli, ENGORDA)
    assert r['nivel_tecnologico']['nivel'] == INDEFINIDO
    assert r['nivel_tecnologico']['ua_ha'] is None
