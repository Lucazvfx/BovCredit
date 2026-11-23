import uuid

import pytest

import database as db
from app import app, primeiro_nome_exibicao


def _login(nome):
    db.init_db()
    email = f'joao123-{uuid.uuid4().hex[:6]}@example.com'
    db.criar_usuario(email, nome, 'senha123')
    u = db.buscar_usuario_email(email)
    client = app.test_client()
    with client.session_transaction() as s:
        s['_user_id'] = str(u['id'])
    return client, u


@pytest.mark.parametrize('nome,email,esperado', [
    ('Maria Souza', 'maria@x.com', 'Maria'),
    ('', 'joao123@x.com', ''),
    (None, 'joao123@x.com', ''),
    ('joao123', 'joao123@x.com', ''),
    ('JOAO123', 'joao123@x.com', ''),
    ('Maria Souza', 'maria.souza@x.com', 'Maria'),
    ('joao@x.com', 'joao@x.com', ''),
    ('João Silva', 'joao123@x.com', 'João'),
])
def test_primeiro_nome_exibicao(nome, email, esperado):
    assert primeiro_nome_exibicao(nome, email) == esperado


def test_app_sem_nome_nao_expoe_handle_na_saudacao():
    client, u = _login('')
    html = client.get('/app').get_data(as_text=True)
    assert '<span id="od-greeting-nome"></span>.</h1>' in html
    prefixo = u['email'].split('@')[0]
    h1 = html[html.index('id="od-cover-title"'):html.index('</h1>')]
    assert prefixo not in h1


def test_atualizar_nome_reflete_no_banco_e_na_sessao():
    client, u = _login('')
    r = client.post('/api/usuario/nome', json={'nome': '  Ana   Paula  '})
    assert r.status_code == 200
    assert r.get_json() == {'ok': True, 'nome': 'Ana Paula', 'primeiro_nome': 'Ana'}
    assert db.buscar_usuario_id(u['id'])['nome'] == 'Ana Paula'
    assert '<span id="od-greeting-nome">, Ana</span>' in client.get('/app').get_data(as_text=True)


@pytest.mark.parametrize('valor', ['', 'A', 'x' * 81, 'a@b.com', '<script>', None, 123, ['Ana']])
def test_atualizar_nome_invalido_400_e_nao_altera(valor):
    client, u = _login('Original')
    assert client.post('/api/usuario/nome', json={'nome': valor}).status_code == 400
    assert db.buscar_usuario_id(u['id'])['nome'] == 'Original'


def test_atualizar_nome_so_afeta_o_proprio_usuario():
    client, u = _login('Um')
    _, outro = _login('Outro')
    client.post('/api/usuario/nome', json={'nome': 'Novo Nome'})
    assert db.buscar_usuario_id(outro['id'])['nome'] == 'Outro'


def test_atualizar_nome_exige_login_e_csrf():
    c = app.test_client()
    assert c.post('/api/usuario/nome', json={'nome': 'Ana'}).status_code in (302, 401)
    client, _ = _login('Fulano')
    client.get('/app')
    client.csrf = False
    assert client.post('/api/usuario/nome', json={'nome': 'Ana'}).status_code == 403


def test_nome_com_espaco_unicode_nao_cola_palavras():
    client, _ = _login('Original')
    r = client.post('/api/usuario/nome', json={'nome': 'Ana\u00a0Paula'})
    assert r.get_json()['nome'] == 'Ana Paula'
