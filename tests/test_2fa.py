"""
Segundo fator (TOTP, RFC 6238) — implementação própria, sem dependência.

São ~60 linhas de HMAC sobre a biblioteca padrão. Trazer um pacote adicionaria
superfície de supply chain no caminho de autenticação, que é o último lugar
onde se quer dependência de terceiro.

Implementação caseira de cripto exige prova. Estes testes cobrem, em ordem de
importância:

1. Conformidade com os vetores oficiais da RFC 6238 — se falhar, nenhum
   aplicativo autenticador do mundo gera o código certo.
2. Reuso de código dentro da janela.
3. A senha sozinha não autentica.
4. Códigos de recuperação de uso único.
"""
import base64
import hashlib
import time

import pytest

import database as db
from app import app
from services import totp


# ── 1. Conformidade com a RFC 6238 ──────────────────────────────────────────
# Apêndice B: segredo ASCII '12345678901234567890', SHA-1, 8 dígitos.
_SEG_RFC = base64.b32encode(b'12345678901234567890').decode().rstrip('=')


@pytest.mark.parametrize('t,esperado', [
    (59,          '94287082'),
    (1111111109,  '07081804'),
    (1111111111,  '14050471'),
    (1234567890,  '89005924'),
    (2000000000,  '69279037'),
    (20000000000, '65353130'),
])
def test_vetores_oficiais_da_rfc6238(t, esperado):
    """
    Se isto falhar, nenhum aplicativo autenticador gera o código que o servidor
    espera — e o 2FA tranca todo mundo fora em vez de proteger.
    """
    assert totp._codigo(totp._decodificar_segredo(_SEG_RFC), t // 30, 8) == esperado


# ── 2. Reuso ────────────────────────────────────────────────────────────────
def test_codigo_nao_vale_duas_vezes():
    """
    Um TOTP vale 30s e a janela aceita ±1 passo — 90s no total. Sem registrar o
    contador usado, quem interceptar o código (ombro, phishing, log) entra
    dentro desse intervalo.
    """
    seg = totp.gerar_segredo()
    codigo = totp.gerar(seg)
    contador = totp.verificar(seg, codigo)
    assert contador is not None
    assert totp.verificar(seg, codigo, contador_minimo=contador + 1) is None


def test_codigo_seguinte_ainda_vale_apos_o_anterior_ser_usado():
    """Bloquear o passado não pode bloquear o futuro."""
    seg = totp.gerar_segredo()
    agora = time.time()
    c1 = totp.gerar(seg, agora)
    cont1 = totp.verificar(seg, c1, agora=agora)
    c2 = totp.gerar(seg, agora + 30)
    assert totp.verificar(seg, c2, agora=agora + 30,
                          contador_minimo=cont1 + 1) is not None


# ── 3. Janela de tolerância ─────────────────────────────────────────────────
@pytest.mark.parametrize('desvio', [-30, 0, 30])
def test_aceita_desvio_de_relogio_de_ate_um_passo(desvio):
    seg = totp.gerar_segredo()
    agora = time.time()
    assert totp.verificar(seg, totp.gerar(seg, agora + desvio), agora=agora) is not None


@pytest.mark.parametrize('desvio', [-120, 120])
def test_recusa_desvio_grande(desvio):
    """
    Janela larga "para o relógio do celular" multiplica a chance de acerto por
    força bruta. ±1 passo cobre desvio real.
    """
    seg = totp.gerar_segredo()
    agora = time.time()
    assert totp.verificar(seg, totp.gerar(seg, agora + desvio), agora=agora) is None


# ── 4. Entradas inválidas ───────────────────────────────────────────────────
@pytest.mark.parametrize('codigo', ['', None, '12345', '1234567', 'abcdef', '   '])
def test_codigo_malformado_e_recusado(codigo):
    assert totp.verificar(totp.gerar_segredo(), codigo) is None


def test_segredo_invalido_nao_levanta():
    """Segredo corrompido no banco não pode virar 500 na tela de login."""
    assert totp.verificar('não-é-base32!', '123456') is None


def test_segredos_diferentes_geram_codigos_diferentes():
    a, b = totp.gerar_segredo(), totp.gerar_segredo()
    assert a != b
    assert totp.verificar(a, totp.gerar(b)) is None


def test_segredo_tem_entropia_suficiente():
    """160 bits — o recomendado pela RFC 4226."""
    assert len(totp._decodificar_segredo(totp.gerar_segredo())) == 20


# ── 5. URI de provisionamento ───────────────────────────────────────────────
def test_uri_traz_emissor_no_rotulo_e_no_parametro():
    """
    Sem o emissor no rótulo, apps antigos mostram só o e-mail e o usuário não
    sabe de qual sistema é a entrada.
    """
    uri = totp.uri_provisionamento('ABC234', 'analista@fazenda.com.br')
    assert uri.startswith('otpauth://totp/')
    assert 'Orkavyn%20Agro%20Intelligence%3Aanalista' in uri
    assert 'issuer=Orkavyn%20Agro%20Intelligence' in uri
    assert 'secret=ABC234' in uri


# ── 6. Códigos de recuperação ───────────────────────────────────────────────
def test_codigos_de_backup_sao_unicos_e_legiveis():
    cods = totp.gerar_codigos_backup()
    assert len(cods) == len(set(cods)) == totp.QTD_BACKUP
    assert all('-' in c for c in cods), 'formato precisa ser anotável à mão'


def test_backup_e_guardado_em_hash():
    """Quem lê o banco não pode entrar."""
    c = totp.gerar_codigos_backup()[0]
    assert totp.hash_codigo_backup(c) != c
    assert len(totp.hash_codigo_backup(c)) == 64


def test_backup_e_conferido_com_tolerancia_de_formatacao():
    c = totp.gerar_codigos_backup()[0]
    hashes = [totp.hash_codigo_backup(c)]
    assert totp.conferir_codigo_backup(c.upper().replace('-', ' '), hashes)


def test_backup_errado_nao_passa():
    hashes = [totp.hash_codigo_backup(x) for x in totp.gerar_codigos_backup()]
    assert totp.conferir_codigo_backup('0000-0000', hashes) is None


# ── 7. O fluxo, ponta a ponta ───────────────────────────────────────────────
@pytest.fixture
def usuario():
    import uuid
    db.init_db()
    email = f'2fa_{uuid.uuid4().hex[:10]}@example.com'
    db.criar_usuario(email, 'Teste 2FA', 'senha123')
    u = db.buscar_usuario_email(email)
    return dict(u), email


def _logado(uid):
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(uid)
    return c


def test_ativar_exige_confirmacao_com_codigo(usuario):
    """
    Ativar direto trancaria fora quem lesse o QR errado. O segredo fica gravado
    inativo até um código provar que o aplicativo funciona.
    """
    u, _ = usuario
    c = _logado(u['id'])
    d = c.post('/api/2fa/iniciar').get_json()
    assert d['segredo'] and d['uri']
    assert db.totp_estado(u['id'])['ativo'] is False

    assert c.post('/api/2fa/confirmar', json={'codigo': '000000'}).status_code == 400
    assert db.totp_estado(u['id'])['ativo'] is False

    r = c.post('/api/2fa/confirmar', json={'codigo': totp.gerar(d['segredo'])})
    assert r.status_code == 200
    assert db.totp_estado(u['id'])['ativo'] is True
    assert len(r.get_json()['codigos_backup']) == totp.QTD_BACKUP


def test_a_senha_sozinha_nao_autentica(usuario):
    """O teste central: com 2FA ativo, acertar a senha não cria sessão."""
    u, email = usuario
    c = _logado(u['id'])
    d = c.post('/api/2fa/iniciar').get_json()
    c.post('/api/2fa/confirmar', json={'codigo': totp.gerar(d['segredo'])})

    novo = app.test_client()
    r = novo.post('/login', data={'email': email, 'senha': 'senha123'})
    assert r.status_code == 302 and '/login/2fa' in r.headers['Location']
    with novo.session_transaction() as s:
        assert '_user_id' not in s, 'sessão criada antes do segundo fator'
        assert s.get('totp_pendente') == u['id']


def test_codigo_correto_completa_o_login(usuario):
    u, email = usuario
    c = _logado(u['id'])
    d = c.post('/api/2fa/iniciar').get_json()
    c.post('/api/2fa/confirmar', json={'codigo': totp.gerar(d['segredo'])})

    novo = app.test_client()
    novo.post('/login', data={'email': email, 'senha': 'senha123'})
    # o código da confirmação já foi consumido; usa o passo seguinte
    codigo = totp.gerar(d['segredo'], time.time() + 30)
    r = novo.post('/login/2fa', data={'codigo': codigo})
    assert r.status_code == 302
    with novo.session_transaction() as s:
        assert s.get('_user_id') == str(u['id'])


def test_codigo_de_recuperacao_entra_e_e_consumido(usuario):
    u, email = usuario
    c = _logado(u['id'])
    d = c.post('/api/2fa/iniciar').get_json()
    backups = c.post('/api/2fa/confirmar',
                     json={'codigo': totp.gerar(d['segredo'])}).get_json()['codigos_backup']

    novo = app.test_client()
    novo.post('/login', data={'email': email, 'senha': 'senha123'})
    assert novo.post('/login/2fa', data={'codigo': backups[0]}).status_code == 302
    assert len(db.totp_estado(u['id'])['backup']) == totp.QTD_BACKUP - 1

    outro = app.test_client()
    outro.post('/login', data={'email': email, 'senha': 'senha123'})
    r = outro.post('/login/2fa', data={'codigo': backups[0]})
    assert r.status_code == 200, 'código de recuperação usado duas vezes'


def test_2fa_pendente_expira(usuario):
    """
    Sessão meio-autenticada esquecida num computador compartilhado é uma senha
    já validada esperando alguém.
    """
    u, email = usuario
    c = _logado(u['id'])
    d = c.post('/api/2fa/iniciar').get_json()
    c.post('/api/2fa/confirmar', json={'codigo': totp.gerar(d['segredo'])})

    novo = app.test_client()
    novo.post('/login', data={'email': email, 'senha': 'senha123'})
    with novo.session_transaction() as s:
        s['totp_desde'] = time.time() - 600
    r = novo.get('/login/2fa')
    assert r.status_code == 302 and '/login' in r.headers['Location']


def test_sem_etapa_pendente_a_rota_redireciona():
    r = app.test_client().get('/login/2fa')
    assert r.status_code == 302


def test_desativar_exige_a_senha(usuario):
    """Sessão sequestrada não pode desligar o segundo fator."""
    u, _ = usuario
    c = _logado(u['id'])
    d = c.post('/api/2fa/iniciar').get_json()
    c.post('/api/2fa/confirmar', json={'codigo': totp.gerar(d['segredo'])})

    assert c.post('/api/2fa/desativar', json={'senha': 'errada'}).status_code == 403
    assert db.totp_estado(u['id'])['ativo'] is True

    assert c.post('/api/2fa/desativar', json={'senha': 'senha123'}).status_code == 200
    assert db.totp_estado(u['id'])['ativo'] is False


def test_desativar_apaga_o_segredo(usuario):
    """Segredo órfão no banco é credencial viva sem dono."""
    u, _ = usuario
    c = _logado(u['id'])
    d = c.post('/api/2fa/iniciar').get_json()
    c.post('/api/2fa/confirmar', json={'codigo': totp.gerar(d['segredo'])})
    c.post('/api/2fa/desativar', json={'senha': 'senha123'})
    est = db.totp_estado(u['id'])
    assert est['segredo'] is None and est['backup'] == []


def test_conta_sem_2fa_entra_direto(usuario):
    u, email = usuario
    c = app.test_client()
    r = c.post('/login', data={'email': email, 'senha': 'senha123'})
    assert r.status_code == 302 and '/login/2fa' not in r.headers['Location']


def test_rotas_de_2fa_exigem_login():
    c = app.test_client()
    for rota in ('/api/2fa/iniciar', '/api/2fa/confirmar', '/api/2fa/desativar'):
        assert c.post(rota, json={}).status_code in (302, 401)
    assert c.get('/api/2fa/estado').status_code in (302, 401)


def test_falha_de_segundo_fator_fica_na_trilha(usuario):
    u, email = usuario
    c = _logado(u['id'])
    d = c.post('/api/2fa/iniciar').get_json()
    c.post('/api/2fa/confirmar', json={'codigo': totp.gerar(d['segredo'])})

    novo = app.test_client()
    novo.post('/login', data={'email': email, 'senha': 'senha123'})
    novo.post('/login/2fa', data={'codigo': '000000'})

    ev = db.listar_acessos(evento='login_2fa_falhou', limit=1)
    assert ev and ev[0]['sucesso'] is False
