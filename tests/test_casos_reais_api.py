import uuid

import pytest

import database as db
from app import app


@pytest.fixture(scope='module')
def client_casos():
    db.init_db()
    email = f'casos-api-{uuid.uuid4().hex}@example.com'
    db.criar_usuario(email, 'Casos API', 'senha123')
    user = db.buscar_usuario_email(email)
    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = str(user['id'])
    return client


def _classificar(client):
    resposta = client.post('/api/classificar', json={
        'valores': [30, 20, 10, 8, 14, 10, 12, 6, 18, 4],
        'origem_dados': 'PDF',
        'arquivo_origem': 'ficha-teste.pdf',
        'estado': 'TO',
        'modelo': 'TO_DECLARACAO',
        'fazenda': 'Fazenda API',
    })
    assert resposta.status_code == 200
    return resposta.get_json()


def test_classificacao_cria_caso_real_pendente(client_casos):
    resultado = _classificar(client_casos)
    resposta = client_casos.get('/api/casos-reais?status=PENDENTE&origem=PDF')
    assert resposta.status_code == 200
    casos = resposta.get_json()['casos']
    caso = next(item for item in casos if item['registro_id'] == resultado['registro_id'])
    assert caso['status'] == 'PENDENTE'
    assert caso['arquivo'] == 'ficha-teste.pdf'
    assert caso['estado'] == 'TO'


def test_confirmar_caso_real_sincroniza_registro(client_casos):
    resultado = _classificar(client_casos)
    caso = next(item for item in client_casos.get('/api/casos-reais').get_json()['casos']
                if item['registro_id'] == resultado['registro_id'])
    resposta = client_casos.post(
        f"/api/casos-reais/{caso['id']}/confirmar",
        json={'classificacao': 'RECRIA', 'observacao': 'Conferido'},
    )
    assert resposta.status_code == 200
    assert resposta.get_json()['caso']['status'] == 'CONFIRMADO'
    registro = db.buscar_registro_por_id(resultado['registro_id'])
    assert registro['class_conf'] == 'RECRIA'


def test_descartar_caso_real_exige_motivo(client_casos):
    resultado = _classificar(client_casos)
    caso = next(item for item in client_casos.get('/api/casos-reais').get_json()['casos']
                if item['registro_id'] == resultado['registro_id'])
    vazio = client_casos.post(f"/api/casos-reais/{caso['id']}/descartar", json={})
    assert vazio.status_code == 400
    ok = client_casos.post(
        f"/api/casos-reais/{caso['id']}/descartar",
        json={'motivo': 'Documento ilegível'},
    )
    assert ok.status_code == 200
    assert ok.get_json()['status'] == 'DESCARTADO'

