"""
Rotas do webhook WhatsApp — e a regra que impede vazamento.

O webhook recebe um número de telefone e nada mais. Sem vínculo explícito,
responder qualquer pergunta sobre um parecer entregaria dado de crédito de um
cliente a quem descobrisse o número do bot. O vínculo só existe se um analista
logado gerar um código de uso único e enviá-lo pelo próprio WhatsApp.
"""
import hashlib
import hmac
import json
import random

import pytest

import database as db
from app import app
from services import whatsapp as wa


@pytest.fixture
def ligado(monkeypatch):
    monkeypatch.setattr(wa, '_TOKEN', 'tok')
    monkeypatch.setattr(wa, '_PHONE_ID', '999')
    monkeypatch.setattr(wa, '_VERIFY_TOKEN', 'vt')
    monkeypatch.setattr(wa, '_APP_SECRET', 'seg')
    enviados = []
    monkeypatch.setattr(wa, 'enviar_mensagem',
                        lambda tel, txt: (enviados.append((tel, txt)), True)[1])
    return enviados


@pytest.fixture
def cli():
    db.init_db()
    return app.test_client()


@pytest.fixture
def analista():
    db.init_db()
    email = 'wa@example.com'
    if not db.buscar_usuario_email(email):
        db.criar_usuario(email, 'Analista WA', 'senha123')
    return db.buscar_usuario_email(email)


def _post(cli, payload, segredo='seg'):
    corpo = json.dumps(payload).encode()
    sig = 'sha256=' + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()
    return cli.post('/webhook/whatsapp', data=corpo,
                    headers={'X-Hub-Signature-256': sig,
                             'Content-Type': 'application/json'})


def _tel():
    """Telefone inédito: o banco local persiste entre execuções, e um número
    fixo já estaria vinculado na segunda rodada."""
    return f'5511{random.randint(900000000, 989999999)}'


def _msg(texto, telefone='5511987654321'):
    return {'entry': [{'changes': [{'value': {
        'messages': [{'from': telefone, 'id': 'w1', 'type': 'text',
                      'text': {'body': texto}}]}}]}]}


# ── Feature flag ────────────────────────────────────────────────────────────
def test_rotas_nao_existem_sem_configuracao(cli, monkeypatch):
    """Quem não configurou não tem webhook exposto."""
    monkeypatch.setattr(wa, '_TOKEN', '')
    monkeypatch.setattr(wa, '_PHONE_ID', '')
    assert cli.get('/webhook/whatsapp').status_code == 404
    assert cli.post('/webhook/whatsapp', json={}).status_code == 404


# ── Handshake ───────────────────────────────────────────────────────────────
def test_handshake_ok(cli, ligado):
    r = cli.get('/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=vt&hub.challenge=42')
    assert r.status_code == 200
    assert r.data == b'42'


def test_handshake_token_errado(cli, ligado):
    r = cli.get('/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=x&hub.challenge=42')
    assert r.status_code == 403


# ── Assinatura na rota ──────────────────────────────────────────────────────
def test_post_sem_assinatura_e_recusado(cli, ligado):
    assert cli.post('/webhook/whatsapp', json=_msg('oi')).status_code == 403


def test_post_com_assinatura_de_outro_segredo_e_recusado(cli, ligado):
    assert _post(cli, _msg('oi'), segredo='atacante').status_code == 403


def test_post_assinado_e_aceito(cli, ligado):
    assert _post(cli, _msg('oi')).status_code == 200


# ── A regra que impede vazamento ────────────────────────────────────────────
def test_telefone_nao_vinculado_nao_recebe_dado_de_credito(cli, ligado, monkeypatch):
    """O teste mais importante do arquivo."""
    chamou = []
    import app as appmod
    monkeypatch.setattr(appmod, '_gerar_resposta_chat_wa',
                        lambda *a, **k: chamou.append(1) or 'DSCR 1,45, aprovado')

    _post(cli, _msg('Qual o DSCR do parecer?', telefone=_tel()))

    assert chamou == [], 'o modelo não pode nem ser consultado para número desconhecido'
    assert len(ligado) == 1
    _, resposta = ligado[0]
    assert 'não vinculado' in resposta.lower()
    assert 'DSCR' not in resposta


def test_codigo_valido_vincula_e_depois_responde(cli, ligado, analista, monkeypatch):
    import app as appmod
    monkeypatch.setattr(appmod, '_gerar_resposta_chat_wa',
                        lambda *a, **k: 'O DSCR do ano crítico é 1,45.')

    tel = _tel()
    codigo = db.criar_codigo_whatsapp(analista['id'])

    _post(cli, _msg(codigo, telefone=tel))
    assert 'vinculado' in ligado[-1][1].lower()

    db.salvar_parecer(analista['id'], None, {'tipo': 'CRIA'},
                      {'conclusao': {'recomendacao': 'aprovar', 'dscr': 1.45},
                       'identificacao': {'fazenda': 'Santa Cruz'}})
    _post(cli, _msg('Qual o DSCR?', telefone=tel))
    assert '1,45' in ligado[-1][1]


def test_codigo_e_de_uso_unico(cli, ligado, analista):
    """Um código vazado depois de usado não pode servir para outro número."""
    codigo = db.criar_codigo_whatsapp(analista['id'])
    assert db.consumir_codigo_whatsapp(codigo, _tel()) == analista['id']
    assert db.consumir_codigo_whatsapp(codigo, _tel()) is None


def test_codigo_invalido_nao_vincula(cli, ligado):
    _post(cli, _msg('000000', telefone=_tel()))
    assert 'inválido' in ligado[-1][1].lower() or 'expirado' in ligado[-1][1].lower()


def test_vinculado_sem_parecer_recebe_instrucao(cli, ligado):
    db.init_db()
    email = 'wa_sem_parecer@example.com'
    if not db.buscar_usuario_email(email):
        db.criar_usuario(email, 'Sem Parecer', 'senha123')
    u = db.buscar_usuario_email(email)
    tel = _tel()
    db.consumir_codigo_whatsapp(db.criar_codigo_whatsapp(u['id']), tel)

    _post(cli, _msg('Qual o DSCR?', telefone=tel))
    assert 'ainda não tem parecer' in ligado[-1][1].lower()


def test_nono_digito_nao_quebra_o_vinculo(cli, ligado, analista, monkeypatch):
    """
    Vinculado com o nono dígito, a Meta entrega sem ele. Se as variantes não
    fossem consultadas, o vínculo simplesmente nunca funcionaria em produção.
    """
    import app as appmod
    monkeypatch.setattr(appmod, '_gerar_resposta_chat_wa', lambda *a, **k: 'resposta ok')

    base = f'{random.randint(70000000, 79999999)}'      # 8 dígitos
    com_nono, sem_nono = f'55119{base}', f'5511{base}'
    db.consumir_codigo_whatsapp(db.criar_codigo_whatsapp(analista['id']), com_nono)
    db.salvar_parecer(analista['id'], None, {}, {'conclusao': {'recomendacao': 'aprovar'}})

    _post(cli, _msg('e aí?', telefone=sem_nono))   # a Meta entrega sem o 9
    assert ligado[-1][1] == 'resposta ok'


# ── Robustez do webhook ─────────────────────────────────────────────────────
def test_falha_ao_responder_nao_devolve_erro_para_a_meta(cli, ligado, analista, monkeypatch):
    """
    500 faz a Meta reenviar em backoff, e o usuário receberia a resposta
    repetida. O webhook engole o erro e confirma o recebimento.
    """
    import app as appmod

    def _explode(*a, **k):
        raise RuntimeError('groq caiu')

    monkeypatch.setattr(appmod, '_responder_whatsapp', _explode)
    assert _post(cli, _msg('oi')).status_code == 200


def test_evento_sem_mensagem_e_aceito_sem_responder(cli, ligado):
    r = _post(cli, {'entry': [{'changes': [{'value': {
        'statuses': [{'id': 'w1', 'status': 'read'}]}}]}]})
    assert r.status_code == 200
    assert ligado == []


# ── Geração do código ───────────────────────────────────────────────────────
def test_gerar_codigo_exige_login(cli, ligado):
    assert cli.post('/api/whatsapp/codigo').status_code in (302, 401)


def test_gerar_codigo_logado(ligado, analista):
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(analista['id'])
    r = c.post('/api/whatsapp/codigo')
    assert r.status_code == 200
    d = r.get_json()
    assert len(d['codigo']) == 6 and d['codigo'].isdigit()


def test_gerar_codigo_indisponivel_sem_configuracao(analista, monkeypatch):
    monkeypatch.setattr(wa, '_TOKEN', '')
    monkeypatch.setattr(wa, '_PHONE_ID', '')
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(analista['id'])
    assert c.post('/api/whatsapp/codigo').status_code == 503
