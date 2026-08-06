import pytest
import database as db_module
from app import app


@pytest.fixture
def client():
    email = 'cotacao-test@example.com'
    u = db_module.buscar_usuario_email(email)
    if not u:
        db_module.criar_usuario(email, 'Cotacao Test', 'senha123')
        u = db_module.buscar_usuario_email(email)
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u['id'])
    return c


def test_precos_live_inclui_bezerro_e_bezerra(client):
    r = client.get('/api/precos/live')
    assert r.status_code == 200
    data = r.get_json()
    assert data['ok'] is True
    p = data['precos']
    assert 'bezerro' in p and p['bezerro'] > 0
    assert 'bezerra' in p and p['bezerra'] > 0
    # bezerra ≈ bezerro × 0,90 quando derivada
    assert p['bezerra'] <= p['bezerro']
