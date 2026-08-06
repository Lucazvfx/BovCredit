"""
Erros precisam chegar ao usuário como mensagem, não como silêncio.

O frontend consome JSON. Quando uma rota /api quebrava, o Flask devolvia a
página HTML padrão de 500; o `res.json()` do navegador lançava, a exceção
subia sem catch e a tela ficava muda — o spinner sumia, nenhum resultado
aparecia e o usuário não tinha o que reportar.

Todo erro em /api passa a devolver JSON com um `trace_id` curto, registrado
também no log do servidor: o usuário informa a referência e ela localiza o
traceback exato.
"""
import pytest

import database as db
from app import app


@pytest.fixture(scope='module')
def client():
    db.init_db()
    email = 'erros@example.com'
    if not db.buscar_usuario_email(email):
        db.criar_usuario(email, 'Erros Test', 'senha123')
    u = db.buscar_usuario_email(email)
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u['id'])
    return c


def test_erro_interno_devolve_json_e_nao_html(client, monkeypatch):
    """
    O caso que deixava a tela muda: exceção inesperada no meio do fluxo.
    Precisa virar JSON — HTML faz o res.json() do navegador lançar.
    """
    import app as appmod

    def explode(*a, **k):
        raise RuntimeError('falha simulada no motor')

    monkeypatch.setattr(appmod, 'calcular_indicadores', explode)
    r = client.post('/api/classificar',
                    json={'valores': [60, 60, 30, 15, 45, 20, 90, 6, 170, 8],
                          'preco': 320})

    assert r.status_code == 500
    assert r.headers['Content-Type'].startswith('application/json'), (
        'erro em /api não pode devolver HTML — o frontend só lê JSON'
    )
    d = r.get_json()
    assert d['erro'], 'o usuário precisa de uma mensagem'
    assert d.get('trace_id'), (
        'sem trace_id o usuário não tem como referenciar o erro no suporte'
    )
    assert len(d['trace_id']) == 8


def test_trace_id_muda_a_cada_erro(client, monkeypatch):
    """Cada ocorrência precisa da própria referência, senão não localiza nada."""
    import app as appmod

    def explode(*a, **k):
        raise RuntimeError('falha simulada')

    monkeypatch.setattr(appmod, 'calcular_indicadores', explode)
    payload = {'valores': [60, 60, 30, 15, 45, 20, 90, 6, 170, 8], 'preco': 320}
    a = client.post('/api/classificar', json=payload).get_json()['trace_id']
    b = client.post('/api/classificar', json=payload).get_json()['trace_id']
    assert a != b


def test_erro_de_validacao_continua_explicando_o_motivo(client):
    """400 não deve virar mensagem genérica — o usuário precisa saber o que corrigir."""
    r = client.post('/api/classificar', json={'valores': [1, 2, 3]})
    assert r.status_code == 400
    d = r.get_json()
    assert 'erro' in d
    assert '10 valores' in d['erro'], 'a mensagem precisa dizer o que está errado'
    assert 'trace_id' not in d, 'erro do usuário não é falha do servidor'


def test_rota_inexistente_em_api_devolve_json(client):
    r = client.get('/api/rota-que-nao-existe')
    assert r.status_code == 404
    assert r.headers['Content-Type'].startswith('application/json')
    assert r.get_json()['status'] == 404


def test_pagina_html_nao_vira_json(client):
    """Fora de /api o comportamento padrão do Flask é preservado."""
    r = client.get('/pagina-que-nao-existe')
    assert r.status_code == 404
    assert not r.headers['Content-Type'].startswith('application/json')
