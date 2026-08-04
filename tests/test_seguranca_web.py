"""Regressões das proteções comuns da interface autenticada."""
import database as db
from app import app


def _cliente_autenticado():
    db.init_db()
    email = 'seguranca-web@example.com'
    u = db.buscar_usuario_email(email)
    if not u:
        db.criar_usuario(email, 'Segurança', 'senha123')
        u = db.buscar_usuario_email(email)
    app.config['TESTING'] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u['id'])
    return c


def test_app_entrega_csp_e_token_csrf():
    c = _cliente_autenticado()
    r = c.get('/app')
    assert r.status_code == 200
    assert r.headers.get('Content-Security-Policy')
    assert b'name="csrf-token"' in r.data


def test_api_autenticada_rejeita_post_sem_csrf_depois_de_renderizar_app():
    c = _cliente_autenticado()
    c.get('/app')  # cria o token da sessão
    r = c.post('/api/fazendas', json={'nome': 'Teste'})
    assert r.status_code == 403


def test_api_autenticada_aceita_header_csrf():
    c = _cliente_autenticado()
    c.get('/app')
    with c.session_transaction() as s:
        token = s['csrf_token']
    r = c.post('/api/fazendas', json={'nome': 'Teste CSRF'},
               headers={'X-CSRF-Token': token})
    assert r.status_code != 403
