"""Limites de entrada: juros_aa (fração) e anos (perene)."""
import uuid

import pytest

import database as db
from app import app
from services.limites_entrada import ANOS_MAX, erro_anos, erro_juros_aa
from tests.test_perene_parecer import _login as _login_perene, _payload as _payload_perene


# ── helpers puros ───────────────────────────────────────────────────────────

@pytest.mark.parametrize('valor', [None, 0, 0.0, 0.105, 0.115, 0.99, '0.12'])
def test_juros_validos_passam(valor):
    assert erro_juros_aa(valor) is None


@pytest.mark.parametrize('valor', [1, 1.0, 10.5, 12, -0.1, float('nan'),
                                   float('inf'), True, 'abc'])
def test_juros_invalidos_sao_recusados(valor):
    assert erro_juros_aa(valor)


@pytest.mark.parametrize('valor', [None, 0, 1, 6, 30, '6', 'abc'])
def test_anos_validos_passam(valor):
    assert erro_anos(valor) is None


@pytest.mark.parametrize('valor', [31, 1000, -1, float('nan'), float('inf')])
def test_anos_invalidos_sao_recusados(valor):
    assert erro_anos(valor)


# ── /api/classificar ────────────────────────────────────────────────────────

def _login_classificar():
    db.init_db()
    email = 'limites@example.com'
    usuario = db.buscar_usuario_email(email)
    if not usuario:
        db.criar_usuario(email, 'Limites', 'senha123')
        usuario = db.buscar_usuario_email(email)
    cliente = app.test_client()
    with cliente.session_transaction() as sessao:
        sessao['_user_id'] = str(usuario['id'])
    return cliente


def _payload_classificar(juros):
    return {'valores': [10, 10, 8, 8, 6, 6, 30, 2, 40, 3], 'preco': 320,
            'custo_arroba': 57, 'credito_valor': 100000, 'prazo_meses': 24,
            'juros_aa': juros}


@pytest.mark.parametrize('juros', [10.5, 1, 100])
def test_classificar_recusa_juros_em_percentual(juros):
    r = _login_classificar().post('/api/classificar',
                                  json=_payload_classificar(juros))
    assert r.status_code == 400
    assert 'fração' in r.get_json()['erro']


@pytest.mark.parametrize('juros', [0, 0.105, 0.99])
def test_classificar_aceita_juros_validos(juros):
    r = _login_classificar().post('/api/classificar',
                                  json=_payload_classificar(juros))
    assert r.status_code == 200


# ── /api/perene/analisar ────────────────────────────────────────────────────

@pytest.mark.parametrize('juros', [-0.1, float('nan'), 10.5])
def test_perene_recusa_juros_invalido(juros):
    payload = _payload_perene()
    payload['credito'] = dict(payload['credito'], juros_aa=juros)
    r = _login_perene().post('/api/perene/analisar', json=payload)
    assert r.status_code == 400
    assert 'juros_aa' in r.get_json()['erro']


@pytest.mark.parametrize('anos', [ANOS_MAX + 1, 100000, -3])
def test_perene_recusa_anos_fora_do_limite(anos):
    r = _login_perene().post('/api/perene/analisar',
                             json=_payload_perene(anos=anos))
    assert r.status_code == 400
    assert 'anos' in r.get_json()['erro']


def test_perene_aceita_anos_no_limite():
    r = _login_perene().post('/api/perene/analisar',
                             json=_payload_perene(anos=ANOS_MAX))
    assert r.status_code == 200


# ── API v1 ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def v1():
    db.init_db()
    email = f'lim-{uuid.uuid4().hex[:8]}@example.com'
    db.criar_usuario(email, 'Lim', 'senha123')
    usuario = db.buscar_usuario_email(email)
    org = db.empresas_do_usuario(usuario['id'])[0]
    chave = db.issue_analysis_api_key(
        organization_id=org['id'], user_id=None, name='t',
        scopes=['payment-capacity:analyze', 'cashflow:project'])['raw_key']
    return app.test_client(), {'X-API-Key': chave}


@pytest.mark.parametrize('rota,corpo', [
    ('/api/v1/payment-capacity',
     lambda j: {'cashflow': {}, 'debt_request': {'credito_valor': 1, 'juros_aa': j}}),
    ('/api/v1/cashflow/project',
     lambda j: {'annual_projection': {'anos': []},
                'debt_schedule': {'credito_valor': 1, 'juros_aa': j}}),
])
@pytest.mark.parametrize('juros', [10.5, -0.1, 'abc'])
def test_v1_recusa_juros_invalido(v1, rota, corpo, juros):
    cliente, cabecalhos = v1
    r = cliente.post(rota, json=corpo(juros), headers=cabecalhos)
    assert r.status_code == 400
    erro = r.get_json()['error']
    assert erro['code'] == 'validation_error'
    assert 'juros_aa' in erro['message']
