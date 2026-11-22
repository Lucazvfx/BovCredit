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


@pytest.mark.parametrize('valor', [None, 0, 1, 6, 30, 30.9, '6', 'abc'])
def test_anos_validos_passam(valor):
    assert erro_anos(valor) is None


@pytest.mark.parametrize('valor', [31, 1000, -1, -0.5, float('nan'), float('inf')])
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


@pytest.mark.parametrize('juros', [0, 0.105, 0.99, '', None, '0.12'])
def test_classificar_aceita_juros_validos(juros):
    r = _login_classificar().post('/api/classificar',
                                  json=_payload_classificar(juros))
    assert r.status_code == 200


def test_classificar_sem_credito_com_juros_valido():
    payload = _payload_classificar(0.105)
    payload['credito_valor'] = 0
    assert _login_classificar().post('/api/classificar', json=payload).status_code == 200


# ── /api/perene/analisar ────────────────────────────────────────────────────

@pytest.mark.parametrize('juros', [-0.1, float('nan'), 10.5])
def test_perene_recusa_juros_invalido(juros):
    payload = _payload_perene()
    payload['credito'] = dict(payload['credito'], juros_aa=juros)
    r = _login_perene().post('/api/perene/analisar', json=payload)
    assert r.status_code == 400
    assert 'juros_aa' in r.get_json()['erro']


@pytest.mark.parametrize('anos', [ANOS_MAX + 1, 100000, -3, float('inf')])
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


@pytest.mark.parametrize('juros', [0.12, None, '0.12'])
def test_v1_aceita_juros_validos(v1, juros):
    cliente, cabecalhos = v1
    corpo = {'cashflow': {}, 'debt_request': {'credito_valor': 1, 'juros_aa': juros}}
    r = cliente.post('/api/v1/payment-capacity', json=corpo, headers=cabecalhos)
    assert r.status_code != 400 or 'juros_aa' not in r.get_json()['error']['message']


# ── rotas irmãs: PDF perene e grãos ─────────────────────────────────────────

@pytest.mark.parametrize('extra', [
    {'anos': float('inf')}, {'anos': ANOS_MAX + 1},
    {'credito': {'juros_aa': 10.5}}, {'credito': {'juros_aa': -0.1}},
])
def test_pdf_perene_recusa_limites(extra):
    payload = dict(_payload_perene(), **extra)
    r = _login_perene().post('/api/perene/parecer/pdf', json=payload)
    assert r.status_code == 400
    assert ('anos' in r.get_json()['erro']) or ('juros_aa' in r.get_json()['erro'])


@pytest.mark.parametrize('juros', [10.5, -0.1, float('nan'), 'abc'])
def test_graos_recusa_juros_invalido(juros):
    r = _login_perene().post('/api/agricola/graos/analisar', json={
        'culturas': [{'cultura': 'SOJA'}], 'credito': {'juros_aa': juros}})
    assert r.status_code == 400
    assert 'juros_aa' in r.get_json()['erro']


# ── API v1: full-analysis e production/project ──────────────────────────────

@pytest.fixture()
def v1_amplo():
    db.init_db()
    email = f'lim-{uuid.uuid4().hex[:8]}@example.com'
    db.criar_usuario(email, 'Lim', 'senha123')
    usuario = db.buscar_usuario_email(email)
    org = db.empresas_do_usuario(usuario['id'])[0]
    chave = db.issue_analysis_api_key(
        organization_id=org['id'], user_id=None, name='t',
        scopes=['analysis:write', 'production:project'])['raw_key']
    return app.test_client(), {'X-API-Key': chave, 'Idempotency-Key': 'k-limites'}


VALORES = [10, 10, 8, 8, 6, 6, 30, 2, 40, 3]


@pytest.mark.parametrize('extra,campo', [
    ({'juros_aa': 10.5}, 'juros_aa'), ({'juros_aa': -0.1}, 'juros_aa'),
    ({'anos': ANOS_MAX + 1}, 'anos'), ({'anos': -2}, 'anos'),
])
def test_v1_full_analysis_recusa_limites(v1_amplo, extra, campo):
    cliente, cabecalhos = v1_amplo
    r = cliente.post('/api/v1/full-analysis', json=dict({'valores': VALORES}, **extra),
                     headers=cabecalhos)
    assert r.status_code == 400
    erro = r.get_json()['error']
    assert erro['code'] == 'validation_error' and campo in erro['message']


@pytest.mark.parametrize('years', [ANOS_MAX + 1, 100000])
def test_v1_production_recusa_years_acima_do_maximo(v1_amplo, years):
    cliente, cabecalhos = v1_amplo
    r = cliente.post('/api/v1/production/project',
                     json={'valores': VALORES, 'system': 'CRIA', 'years': years},
                     headers=cabecalhos)
    assert r.status_code == 400
    assert 'years' in r.get_json()['error']['message']


def test_v1_production_aceita_years_no_maximo(v1_amplo):
    cliente, cabecalhos = v1_amplo
    r = cliente.post('/api/v1/production/project',
                     json={'valores': VALORES, 'system': 'CRIA', 'years': ANOS_MAX},
                     headers=cabecalhos)
    assert r.status_code == 200
