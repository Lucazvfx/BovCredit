"""O motor de retenção ficou para trás na correção da base reprodutiva.

`test_base_reprodutiva.py` tirou a faixa de 25–36m de cima da produção de
bezerro nos motores de cria e ciclo completo. O bloco que alimenta
`calcular_retencao` em app.py continuou somando as duas faixas e projetando
desmama em cima do total.

Medido na cria de referência (600 matrizes reais, 150 fêmeas de 25–36m):

    base usada ............ 750 contra 600
    bezerras desmamadas ... 215 contra 172

São 43 bezerras por ano que não nascem, entrando na conta de quantas a
fazenda pode reter — e retenção vira capacidade de pagamento no parecer.
"""
import pytest

import database as db
from app import app
from services.base_reprodutiva import base_reprodutiva

CRIA = [300, 280, 200, 80, 100, 40, 150, 10, 600, 15]


@pytest.fixture(scope='module')
def cli():
    db.init_db()
    email = 'retencaobase@example.com'
    u = db.buscar_usuario_email(email)
    if not u:
        db.criar_usuario(email, 'Retencao', 'senha123')
        u = db.buscar_usuario_email(email)
    app.config['TESTING'] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u['id'])
    return c


def test_a_faixa_25_36m_nao_entra_na_reposicao_da_retencao(cli):
    """Reposição necessária sai de matrizes × descarte — de quem já pariu."""
    r = cli.post('/api/classificar', json={
        'valores': CRIA, 'preco': 330,
        'taxa_descarte_pct': 15.0,
        'natalidade_pct': 70.0,
        'desmama_pct': 82.0,
    }).get_json()

    zoo = r['analise_retencao']['limite_zootecnico']
    esperado = CRIA[8] * 0.15
    antigo = (CRIA[6] + CRIA[8]) * 0.15
    assert zoo['reposicao_necessaria'] == pytest.approx(esperado, rel=0.01), (
        f"reposição de {zoo['reposicao_necessaria']} para {CRIA[8]} matrizes — "
        f'a faixa de 25–36m voltou para a base da retenção'
    )
    assert zoo['reposicao_necessaria'] < antigo * 0.9


def test_a_desmama_projetada_sai_das_matrizes_reais(cli):
    """A retenção informada é medida contra a desmama de quem já pariu.

    `retencao_bezerras_pct` divide as bezerras retidas pelas desmamadas. Com a
    base inflada, o denominador cresce e a retenção informada parece menor do
    que é — o alerta de retenção excessiva deixa de disparar.
    """
    r = cli.post('/api/classificar', json={
        'valores': CRIA, 'preco': 330,
        'natalidade_pct': 70.0,
        'desmama_pct': 82.0,
        'bezerras_retidas': 100.0,
    }).get_json()

    pct = r['analise_retencao']['fases']['retencao_bezerras_pct']
    desmamadas_reais = CRIA[8] * 0.70 * 0.82 * 0.5
    desmamadas_antigas = (CRIA[6] + CRIA[8]) * 0.70 * 0.82 * 0.5
    assert pct == pytest.approx(100.0 / desmamadas_reais * 100, rel=0.02)
    assert pct > 100.0 / desmamadas_antigas * 100 * 1.1


# ── A função única ──────────────────────────────────────────────────────────
def test_base_separa_quem_pare_de_quem_vai_parir():
    base = base_reprodutiva(CRIA)

    assert base.matrizes == 600
    assert base.prestes == 150
    assert base.plantel_adulto == 750


def test_base_tolera_vetor_incompleto():
    base = base_reprodutiva([1, 2, 3])

    assert base.matrizes == 0.0
    assert base.prestes == 0.0
