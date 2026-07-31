"""
Confirmação do ciclo pelo analista — o loop de dado real.

Todo o conjunto de treino do projeto é sintético, gerado a partir das faixas
de referência que nós mesmos escrevemos. A acurácia medida sobre ele diz
apenas que o modelo aprendeu essas faixas — é validação circular.

Este endpoint é o único caminho pelo qual entra dado rotulado por humano. O
retreino consome exclusivamente `class_conf` (db.exportar_treino), de modo
que a previsão do modelo nunca realimenta a si mesma.
"""
import pytest

import database as db
from app import app


@pytest.fixture(scope='module')
def client():
    db.init_db()
    email = 'confirmacao@example.com'
    if not db.buscar_usuario_email(email):
        db.criar_usuario(email, 'Confirmacao Test', 'senha123')
    u = db.buscar_usuario_email(email)
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u['id'])
    return c


REBANHO_CC = [80, 80, 50, 50, 60, 60, 90, 40, 220, 60]


def _classificar(client, v=None):
    r = client.post('/api/classificar', json={'valores': v or REBANHO_CC, 'preco': 320})
    assert r.status_code == 200
    return r.get_json()


def test_analista_confirma_a_classificacao(client):
    d = _classificar(client)
    r = client.post('/api/confirmar-ciclo',
                    json={'registro_id': d['registro_id'], 'ciclo': d['tipo']})
    assert r.status_code == 200
    body = r.get_json()
    assert body['ok'] is True
    assert body['concordou'] is True
    assert body['ciclo'] == d['tipo']


def test_analista_corrige_a_classificacao(client):
    """A correção vale mais que a confirmação — é ela que ensina."""
    d = _classificar(client)
    outro = 'CRIA_RECRIA' if d['tipo'] != 'CRIA_RECRIA' else 'CRIA'
    r = client.post('/api/confirmar-ciclo',
                    json={'registro_id': d['registro_id'], 'ciclo': outro})
    assert r.status_code == 200
    body = r.get_json()
    assert body['concordou'] is False
    assert body['class_ml'] == d['tipo']
    assert body['ciclo'] == outro


def test_confirmacao_entra_no_conjunto_de_retreino(client):
    """Sem isso o loop não fecha e o dado real não serve para nada."""
    antes = len(db.exportar_treino()[0])
    d = _classificar(client)
    client.post('/api/confirmar-ciclo',
                json={'registro_id': d['registro_id'], 'ciclo': d['tipo']})
    depois = len(db.exportar_treino()[0])
    assert depois == antes + 1, 'a confirmação precisa chegar ao exportar_treino'


def test_contador_de_confirmados_acompanha(client):
    antes = db.contar_confirmados()
    d = _classificar(client)
    r = client.post('/api/confirmar-ciclo',
                    json={'registro_id': d['registro_id'], 'ciclo': d['tipo']})
    assert r.get_json()['total_confirmados'] == antes + 1


def test_todas_as_modalidades_sao_aceitas(client):
    """O analista precisa poder apontar qualquer uma das seis."""
    from ml_engine import TIPOS
    for t in TIPOS:
        d = _classificar(client)
        r = client.post('/api/confirmar-ciclo',
                        json={'registro_id': d['registro_id'], 'ciclo': t})
        assert r.status_code == 200, f'modalidade {t} rejeitada'


@pytest.mark.parametrize('payload,esperado', [
    ({'registro_id': 1, 'ciclo': 'BANANA'}, 400),
    ({'ciclo': 'CRIA'},                     400),
    ({'registro_id': 999999, 'ciclo': 'CRIA'}, 404),
])
def test_entradas_invalidas(client, payload, esperado):
    assert client.post('/api/confirmar-ciclo', json=payload).status_code == esperado


def test_exige_login():
    r = app.test_client().post('/api/confirmar-ciclo',
                               json={'registro_id': 1, 'ciclo': 'CRIA'})
    assert r.status_code in (302, 401)


def test_retreino_nao_realimenta_a_propria_previsao(client):
    """
    Invariante: o conjunto de retreino vem de `class_conf` (humano), nunca de
    `class_ml` (modelo). Se um registro não foi confirmado, não pode entrar.
    """
    # Rebanho com valores únicos, para não colidir com outro já confirmado
    unico = [77, 73, 41, 37, 59, 53, 91, 43, 217, 61]
    d = _classificar(client, unico)   # classificado, mas NÃO confirmado
    X, _ = db.exportar_treino()
    assert [float(x) for x in unico] not in X, (
        'registro não confirmado entrou no conjunto de treino — o modelo '
        'estaria aprendendo com a própria previsão'
    )

    # depois de confirmado, aí sim entra
    client.post('/api/confirmar-ciclo',
                json={'registro_id': d['registro_id'], 'ciclo': d['tipo']})
    X2, _ = db.exportar_treino()
    assert [float(x) for x in unico] in X2
