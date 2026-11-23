import uuid

import database as db
from app import app


def _login_client(nome):
    db.init_db()
    email = f'{nome}-{uuid.uuid4().hex[:8]}@example.com'
    db.criar_usuario(email, nome, 'senha123')
    u = db.buscar_usuario_email(email)
    client = app.test_client()
    with client.session_transaction() as s:
        s['_user_id'] = str(u['id'])
    return client


def test_empresa_perfil_post_e_get():
    client = _login_client('EmpresaPerfil1')
    r = client.post('/api/empresa/perfil', json={
        'nome_consultoria': 'Consultoria Empresa Teste', 'logo_base64': 'YWJj'})
    assert r.status_code == 200
    r2 = client.get('/api/empresa/perfil')
    d = r2.get_json()
    assert d['nome_consultoria'] == 'Consultoria Empresa Teste'
    assert d['logo_base64'] == 'YWJj'


def _analista_da(empresa_id):
    db.init_db()
    email = f'analista-{uuid.uuid4().hex[:8]}@example.com'
    uid = db.criar_usuario(email, 'Analista', 'senha123')
    db._exec(f'UPDATE empresa_membros SET empresa_id={db._PH}, papel={db._PH} '
             f'WHERE user_id={db._PH}', (empresa_id, 'analista', uid), commit=True)
    client = app.test_client()
    with client.session_transaction() as s:
        s['_user_id'] = str(uid)
    return client


def _empresa_do(client):
    with client.session_transaction() as s:
        uid = int(s['_user_id'])
    return db.empresas_do_usuario(uid)[0]['id']


def test_empresa_perfil_post_recusado_para_analista_e_nada_muda():
    admin = _login_client('PerfilAdm')
    admin.post('/api/empresa/perfil', json={'nome_consultoria': 'Nome Original', 'logo_base64': 'YWJj'})
    analista = _analista_da(_empresa_do(admin))
    r = analista.post('/api/empresa/perfil', json={'nome_consultoria': 'Invasor', 'logo_base64': 'eHl6'})
    assert r.status_code == 403
    d = analista.get('/api/empresa/perfil').get_json()  # leitura continua aberta
    assert d['nome_consultoria'] == 'Nome Original' and d['logo_base64'] == 'YWJj'


def test_empresa_perfil_admin_de_uma_empresa_nao_altera_outra():
    a, b = _login_client('PerfilA'), _login_client('PerfilB')
    b.post('/api/empresa/perfil', json={'nome_consultoria': 'Empresa B', 'logo_base64': ''})
    a.post('/api/empresa/perfil', json={'nome_consultoria': 'Empresa A', 'logo_base64': ''})
    assert b.get('/api/empresa/perfil').get_json()['nome_consultoria'] == 'Empresa B'
