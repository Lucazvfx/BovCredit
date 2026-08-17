"""/api/situacao-cadastral — a rota, o consentimento, e a auditoria.

A consulta em si (services/situacao_cadastral.py) já tem testes próprios com
mocks de rede. Aqui o que importa é o contrato HTTP: exige login, exige
consentimento antes de consultar, e audita só quando algo foi realmente
verificado — CPF nunca dispara consulta, então nunca gera evento de auditoria
de consulta bem-sucedida.
"""
import requests

import database as db
import services.auditoria as _aud
from app import app

CNPJ_VALIDO = '12345678000195'
CPF_VALIDO = '12345678909'


class _Resp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def _cli(email='situacaocadastral@example.com'):
    db.init_db()
    u = db.buscar_usuario_email(email)
    if not u:
        db.criar_usuario(email, 'SitCad', 'senha123')
        u = db.buscar_usuario_email(email)
    app.config['TESTING'] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u['id'])
    return c, u['id']


def test_exige_login():
    app.config['TESTING'] = True
    c = app.test_client()
    r = c.post('/api/situacao-cadastral', json={'documento': CNPJ_VALIDO, 'consentimento': True})
    assert r.status_code in (302, 401)


def test_exige_documento(monkeypatch):
    cli, _ = _cli()
    r = cli.post('/api/situacao-cadastral', json={'consentimento': True})
    assert r.status_code == 400


def test_exige_consentimento_antes_de_consultar(monkeypatch):
    def _explode(*a, **k):
        raise AssertionError('não deveria consultar sem consentimento')
    monkeypatch.setattr(requests, 'get', _explode)
    cli, _ = _cli()

    r = cli.post('/api/situacao-cadastral', json={'documento': CNPJ_VALIDO})

    assert r.status_code == 400
    assert 'consentimento' in r.get_json()['erro'].lower() or 'informado' in r.get_json()['erro'].lower()


def test_cnpj_ativo_com_consentimento(monkeypatch):
    monkeypatch.setattr(requests, 'get', lambda *a, **k: _Resp(200, {
        'descricao_situacao_cadastral': 'ATIVA', 'razao_social': 'TESTE LTDA'}))
    cli, _ = _cli()

    r = cli.post('/api/situacao-cadastral',
                 json={'documento': CNPJ_VALIDO, 'consentimento': True})

    assert r.status_code == 200
    d = r.get_json()
    assert d['encontrado'] is True
    assert d['situacao'] == 'ATIVA'


def test_cpf_nunca_dispara_rede_mesmo_com_consentimento(monkeypatch):
    def _explode(*a, **k):
        raise AssertionError('CPF não deveria disparar chamada de rede')
    monkeypatch.setattr(requests, 'get', _explode)
    cli, _ = _cli()

    r = cli.post('/api/situacao-cadastral',
                 json={'documento': CPF_VALIDO, 'consentimento': True})

    assert r.status_code == 200
    d = r.get_json()
    assert d['disponivel'] is False


# ── Auditoria ────────────────────────────────────────────────────────────────
def test_consulta_de_cnpj_gera_evento_de_auditoria(monkeypatch):
    monkeypatch.setattr(requests, 'get', lambda *a, **k: _Resp(200, {
        'descricao_situacao_cadastral': 'ATIVA'}))
    cli, uid = _cli()

    cli.post('/api/situacao-cadastral',
             json={'documento': CNPJ_VALIDO, 'consentimento': True})

    eventos = db.listar_acessos(user_id=uid, limit=5)
    assert any(e.get('evento') == _aud.CONSULTA_CADASTRAL for e in eventos)


def test_consulta_de_cpf_nao_gera_evento_de_auditoria(monkeypatch):
    """CPF nunca consulta nada de verdade — auditar seria registrar um fato
    que não aconteceu."""
    monkeypatch.setattr(requests, 'get',
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
    # Usuário dedicado: os outros testes deste arquivo reaproveitam o mesmo
    # e-mail e o SQLite persiste entre testes — com um usuário compartilhado,
    # o evento de CNPJ de outro teste apareceria nos "últimos 5" e mascararia
    # exatamente o que este teste verifica.
    cli, uid = _cli(email='situacaocadastral-cpf@example.com')

    cli.post('/api/situacao-cadastral',
             json={'documento': CPF_VALIDO, 'consentimento': True})

    eventos = db.listar_acessos(user_id=uid, limit=5)
    assert not any(e.get('evento') == _aud.CONSULTA_CADASTRAL for e in eventos)


# ── O evento existe no catálogo ─────────────────────────────────────────────
def test_evento_esta_no_catalogo_e_e_sensivel():
    assert _aud.CONSULTA_CADASTRAL in _aud.EVENTOS
    assert _aud.e_sensivel(_aud.CONSULTA_CADASTRAL) is True


# ── A tela expõe o campo e o envia ──────────────────────────────────────────
def test_a_tela_tem_o_painel_e_o_checkbox_de_consentimento():
    from pathlib import Path
    html = (Path(__file__).parents[1] / 'templates' / 'index.html').read_text(encoding='utf-8')

    assert 'id="sc-documento"' in html
    assert 'id="sc-consentimento"' in html
    assert "fetch('/api/situacao-cadastral'" in html
    assert 'consentimento' in html.split("fetch('/api/situacao-cadastral'")[1][:400]


# ── LGPD: documentado no inventário ─────────────────────────────────────────
def test_inventario_lgpd_documenta_a_consulta():
    """A consulta não ganha tabela própria — vive dentro de auditoria_acessos
    (campo `detalhe`), então é lá que o inventário precisa declará-la."""
    from services.lgpd import INVENTARIO
    entrada = INVENTARIO['auditoria_acessos']
    assert 'cadastral' in entrada['finalidade'].lower()
    assert 'produtor' in entrada['titular'] or 'empresa' in entrada['titular']
