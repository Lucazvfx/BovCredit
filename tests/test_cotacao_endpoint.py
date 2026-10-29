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


def test_precos_live_ve_cotacao_gravada_por_outro_processo(client):
    """
    O scraper roda no master do gunicorn; os workers são forks com memória
    própria. Uma gravação feita lá não passa por este processo — o endpoint
    tem de enxergá-la mesmo assim, e não servir o preço de antes.
    """
    db_module.guardar_cotacao_diaria({'boi': 311.0, 'vaca': 290.0})
    assert client.get('/api/precos/live').get_json()['precos']['boi'] == 311.0

    db_module.guardar_cotacao_diaria({'boi': 333.0, 'vaca': 300.0})
    assert client.get('/api/precos/live').get_json()['precos']['boi'] == 333.0
