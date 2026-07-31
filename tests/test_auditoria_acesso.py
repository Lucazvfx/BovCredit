"""
Trilha de auditoria de acesso — quem viu o quê, quando, de onde.

Sem isto uma instituição não consegue responder à própria auditoria interna
sobre quem consultou dado de crédito de qual cliente. Essa pergunta aparece na
área de compras antes de qualquer discussão sobre modelo: é o item que barra a
venda para banco, não a acurácia.

Não confundir com `consistencia_rebanho`, que audita o REBANHO declarado. Esta
audita o USO do sistema.
"""
import pytest

import database as db
from app import app
from services import auditoria as aud


@pytest.fixture(scope='module')
def analista():
    db.init_db()
    email = 'auditoria@example.com'
    if not db.buscar_usuario_email(email):
        db.criar_usuario(email, 'Analista Auditoria', 'senha123')
    return db.buscar_usuario_email(email)


@pytest.fixture
def client(analista):
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(analista['id'])
    return c


REBANHO = [60, 60, 30, 15, 45, 20, 90, 6, 170, 8]


def _ultimo(evento):
    itens = db.listar_acessos(evento=evento, limit=1)
    return itens[0] if itens else None


# ── As três regras do módulo ────────────────────────────────────────────────
def test_falha_ao_auditar_nunca_derruba_a_operacao(monkeypatch):
    """
    Um parecer não pode falhar porque a auditoria caiu — e um sistema que falha
    assim acaba com a auditoria desligada na primeira sexta-feira ruim.
    """
    def _explode(*a, **k):
        raise RuntimeError('banco fora do ar')

    monkeypatch.setattr(db, '_exec', _explode)
    db.registrar_acesso('parecer_gerado', user_id=1)   # não pode levantar


def test_a_trilha_nao_duplica_o_dado_sensivel():
    """
    Registra a REFERÊNCIA, não o conteúdo. Copiar o rebanho para uma segunda
    tabela só multiplicaria a superfície de vazamento do que se quer proteger.
    """
    colunas = set(db.listar_acessos(limit=1)[0]) if db.contar_acessos() else set()
    if colunas:
        assert 'valores' not in colunas
        assert 'parecer' not in colunas


def test_nao_existe_rota_de_escrita_nem_de_exclusao():
    """Append-only por desenho: trilha que se edita não é trilha."""
    rotas = {str(r.rule) for r in app.url_map.iter_rules() if 'auditoria' in str(r.rule)}
    for r in rotas:
        metodos = set()
        for regra in app.url_map.iter_rules():
            if str(regra.rule) == r:
                metodos |= regra.methods
        assert metodos <= {'GET', 'HEAD', 'OPTIONS'}, f'{r} aceita escrita'


# ── Eventos que a auditoria interna pede primeiro ───────────────────────────
def test_gerar_parecer_deixa_rastro(client):
    antes = db.contar_acessos()
    r = client.post('/api/classificar', json={'valores': REBANHO, 'preco': 320})
    assert r.status_code == 200
    assert db.contar_acessos() > antes

    ev = _ultimo(aud.PARECER_GERADO)
    assert ev is not None
    assert ev['user_email'] == 'auditoria@example.com'
    assert ev['sucesso'] is True


def test_baixar_pdf_deixa_rastro(client):
    r = client.post('/api/parecer/pdf', json={'parecer': {
        'identificacao': {'fazenda': 'Fazenda Teste'},
        'conclusao': {'recomendacao': 'aprovar'},
    }})
    assert r.status_code == 200
    ev = _ultimo(aud.PARECER_PDF)
    assert ev and ev['recurso_id'] == 'Fazenda Teste'
    assert ev['detalhe'] == 'aprovar'


def test_login_bem_sucedido_e_registrado():
    c = app.test_client()
    db.init_db()
    email = 'aud_login@example.com'
    if not db.buscar_usuario_email(email):
        db.criar_usuario(email, 'Login Aud', 'senha123')
    c.post('/login', data={'email': email, 'senha': 'senha123'})
    ev = _ultimo(aud.LOGIN)
    assert ev and ev['user_email'] == email


def test_login_recusado_e_registrado_como_insucesso():
    """
    O evento mais importante para detectar tentativa de invasão — e o único que
    precisa gravar o e-mail de alguém que não está autenticado.
    """
    c = app.test_client()
    c.post('/login', data={'email': 'invasor@example.com', 'senha': 'errada'})
    ev = _ultimo(aud.LOGIN_FALHOU)
    assert ev is not None
    assert ev['user_email'] == 'invasor@example.com'
    assert ev['sucesso'] is False
    assert ev['user_id'] is None


def test_confirmar_ciclo_deixa_rastro(client):
    d = client.post('/api/classificar',
                    json={'valores': REBANHO, 'preco': 320}).get_json()
    client.post('/api/confirmar-ciclo',
                json={'registro_id': d['registro_id'], 'ciclo': d['tipo']})
    ev = _ultimo(aud.CICLO_CONFIRMADO)
    assert ev and 'analista=' in (ev['detalhe'] or '')


# ── IP atrás de proxy ───────────────────────────────────────────────────────
def test_ip_vem_do_x_forwarded_for(client):
    """
    Railway e qualquer PaaS ficam na frente da app: sem ler o header, a trilha
    registraria o IP do balanceador para todo mundo — e não serviria para nada.
    """
    client.post('/api/classificar', json={'valores': REBANHO, 'preco': 320},
                headers={'X-Forwarded-For': '203.0.113.7, 10.0.0.1'})
    assert _ultimo(aud.PARECER_GERADO)['ip'] == '203.0.113.7'


def test_cadeia_longa_de_proxy_nao_estoura_a_coluna():
    class _Req:
        headers = {'X-Forwarded-For': ', '.join(['203.0.113.7'] * 200)}
        remote_addr = '10.0.0.1'
    assert len(aud.ip_da_requisicao(_Req())) <= 64


def test_sem_header_usa_remote_addr():
    class _Req:
        headers = {}
        remote_addr = '10.0.0.1'
    assert aud.ip_da_requisicao(_Req()) == '10.0.0.1'


# ── Consulta ────────────────────────────────────────────────────────────────
def test_consulta_exige_administrador(client):
    """
    A trilha diz quem consultou dado de crédito de qual cliente — ela própria é
    dado sensível, e um analista comum não pode lê-la.
    """
    assert client.get('/api/admin/auditoria').status_code in (302, 401, 403)


def test_consulta_sem_login_e_recusada():
    assert app.test_client().get('/api/admin/auditoria').status_code in (302, 401, 403)


def test_filtro_por_evento():
    db.registrar_acesso(aud.LOGOUT, user_id=999, user_email='x@y.com')
    itens = db.listar_acessos(evento=aud.LOGOUT, limit=5)
    assert itens and all(i['evento'] == aud.LOGOUT for i in itens)


def test_ordem_e_do_mais_recente_para_o_mais_antigo():
    db.registrar_acesso(aud.LOGOUT, user_id=1001, user_email='primeiro@x.com')
    db.registrar_acesso(aud.LOGOUT, user_id=1002, user_email='segundo@x.com')
    itens = db.listar_acessos(evento=aud.LOGOUT, limit=2)
    assert itens[0]['user_email'] == 'segundo@x.com'


# ── Catálogo de eventos ─────────────────────────────────────────────────────
def test_todo_evento_tem_rotulo_legivel():
    for ev in aud.EVENTOS:
        assert aud.rotulo(ev) != ev, f'{ev} sem rótulo para o auditor'


def test_eventos_sensiveis_sao_os_que_tocam_credito():
    assert aud.e_sensivel(aud.PARECER_GERADO)
    assert aud.e_sensivel(aud.PARECER_PDF)
    assert aud.e_sensivel(aud.HISTORICO_LIDO)
    assert not aud.e_sensivel(aud.LOGIN)
    assert not aud.e_sensivel(aud.LOGOUT)


def test_evento_desconhecido_nao_quebra_o_rotulo():
    assert aud.rotulo('evento_que_nao_existe') == 'evento_que_nao_existe'
