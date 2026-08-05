import pytest
import database as db
from app import app


@pytest.fixture
def client():
    db.init_db()
    email = 'transparencia_test@example.com'
    u = db.buscar_usuario_email(email)
    if not u:
        db.criar_usuario(email, 'Transparência Teste', 'senha123')
        u = db.buscar_usuario_email(email)
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u['id'])
    return c


def test_api_expoe_transparencia_e_cenarios(client):
    r = client.post('/api/classificar', json={
        'valores': [300, 280, 563, 187, 1105, 1344, 298, 80, 593, 39],
        'preco': 320,
    })
    assert r.status_code == 200
    d = r.get_json()
    assert 'campos' in d['qualidade_dados']
    assert 'explicacao_classificacao' in d
    assert 'validacoes_zootecnicas' in d
    assert [x['id'] for x in d['comparacao_cenarios']['cenarios']] == [
        'base_estimado', 'conservador', 'provavel', 'otimista']
