import uuid

import database as db
import app as app_module
from app import app


def _login_admin_client():
    """`is_admin` checa o e-mail contra app._ADMIN_EMAILS (populado via env
    var ADMIN_EMAILS em produção); em teste, adiciona direto no set."""
    db.init_db()
    email = 'admintest@example.com'
    app_module._ADMIN_EMAILS.add(email)
    u = db.buscar_usuario_email(email)
    if not u:
        db.criar_usuario(email, 'Admin Test', 'senha123')
        u = db.buscar_usuario_email(email)
    client = app.test_client()
    with client.session_transaction() as s:
        s['_user_id'] = str(u['id'])
        # Rotas /admin exigem CSRF (app._verificar_csrf_admin). Semeia o token
        # na sessão e devolve-o para que os POSTs de teste o enviem.
        s['csrf_token'] = 'token-de-teste-csrf'
    client._csrf = 'token-de-teste-csrf'
    return client


def test_admin_cria_empresa():
    client = _login_admin_client()
    r = client.post('/admin/empresas/criar',
                    data={'nome': 'Empresa Via Admin', 'csrf_token': client._csrf})
    assert r.status_code in (200, 302)


def test_admin_rejeita_post_sem_csrf():
    """Regressão: a proteção CSRF de /admin deve devolver 403, não 500."""
    client = _login_admin_client()
    r = client.post('/admin/empresas/criar', data={'nome': 'Sem Token'})
    assert r.status_code == 403


def test_admin_vincula_e_desvincula_usuario():
    db.init_db()
    client = _login_admin_client()
    eid = db._exec(f"INSERT INTO empresas (nome) VALUES ({db._PH})",
                   ('Empresa Vinculo',), fetch='lastrow', commit=True)
    alvo_id = db.criar_usuario(f'alvovinculo-{uuid.uuid4().hex[:8]}@example.com',
                               'Alvo Vinculo', 'senha123')

    r = client.post('/admin/empresas/vincular',
                    data={'user_id': alvo_id, 'empresa_id': eid, 'csrf_token': client._csrf})
    assert r.status_code in (200, 302)
    assert db.usuario_pertence_a_empresa(alvo_id, eid)

    r2 = client.post('/admin/empresas/desvincular',
                     data={'user_id': alvo_id, 'empresa_id': eid, 'csrf_token': client._csrf})
    assert r2.status_code in (200, 302)
    assert not db.usuario_pertence_a_empresa(alvo_id, eid)
