"""Regressões das correções de segurança da auditoria de 17/08/2026.

Cada teste aqui trava um buraco que já esteve aberto em produção. Se algum
voltar a passar por acidente numa refatoração, é para a suíte gritar.
"""
import database as db
import pytest
from app import app

from services.api_v1.authentication import APIKeyIdentity


# ── Chave de API sem escopo não autoriza nada ────────────────────────────────

def _identidade(escopos):
    return APIKeyIdentity(
        api_key_id=1, organization_id=1, user_id=None,
        name='teste', scopes=tuple(escopos), key_prefix='lii_00000000',
    )


def test_chave_sem_escopo_nao_abre_rota_nenhuma():
    """O caso provável não é ataque, é descuido: chave criada sem escopo.

    Antes, lista vazia caía num `or not granted` e liberava tudo.
    """
    assert _identidade([]).allows(('herd:analyze',)) is False
    assert _identidade([]).allows(('analysis:write',)) is False


def test_escopo_curinga_continua_valendo():
    """`*` é um "tudo" que alguém escolheu — diferente de não escolher nada."""
    assert _identidade(['*']).allows(('herd:analyze',)) is True


def test_escopo_certo_autoriza_e_escopo_errado_nao():
    ident = _identidade(['herd:analyze'])
    assert ident.allows(('herd:analyze',)) is True
    assert ident.allows(('analysis:write',)) is False


# ── CSRF fecha para sessão sem token ─────────────────────────────────────────

def _cliente_logado():
    db.init_db()
    email = 'csrf-auditoria@example.com'
    u = db.buscar_usuario_email(email)
    if not u:
        db.criar_usuario(email, 'CSRF', 'senha123')
        u = db.buscar_usuario_email(email)
    app.config['TESTING'] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s['_user_id'] = str(u['id'])
    return c


def test_sessao_sem_token_csrf_nao_passa_fora_do_admin():
    """O buraco antigo: `if not esperado and not path.startswith('/admin')`.

    Uma sessão que nunca renderizou página fazia POST sem token nenhum, que é
    exatamente o request que um site malicioso consegue forjar com o cookie
    da vítima. Só /admin fechava.
    """
    c = _cliente_logado()
    c.csrf = False   # sessão crua, sem token semeado nem header
    r = c.post('/api/fazendas', json={'nome': 'Forjada'})
    assert r.status_code == 403


def test_token_errado_tambem_nao_passa():
    c = _cliente_logado()
    with c.session_transaction() as s:
        s['csrf_token'] = 'o-token-certo'
    c.csrf = False
    r = c.post('/api/fazendas', json={'nome': 'Forjada'},
               headers={'X-CSRF-Token': 'o-token-errado'})
    assert r.status_code == 403


# ── Token de reset guardado por hash ─────────────────────────────────────────

def test_token_de_reset_nao_fica_em_claro_no_banco():
    """Um dump do banco não pode entregar reset de senha de ninguém."""
    db.init_db()
    email = 'reset-hash@example.com'
    if not db.buscar_usuario_email(email):
        db.criar_usuario(email, 'Reset', 'senha123')

    token = db.criar_token_reset(email)

    guardado = db._exec(
        f'SELECT token FROM reset_tokens WHERE email={db._PH} AND used=0',
        (email,), fetch='one',
    )
    assert guardado is not None
    assert guardado['token'] != token, 'o token foi gravado em claro'
    assert guardado['token'] == db._hash_token_reset(token)


def test_o_token_original_continua_validando_e_sendo_consumido():
    """Guardar hash não pode quebrar o fluxo de quem recebeu o e-mail."""
    db.init_db()
    email = 'reset-hash-fluxo@example.com'
    if not db.buscar_usuario_email(email):
        db.criar_usuario(email, 'Reset Fluxo', 'senha123')

    token = db.criar_token_reset(email)
    assert db.validar_token_reset(token) == email

    db.consumir_token_reset(token)
    assert db.validar_token_reset(token) is None


def test_hash_de_reset_nao_valida_como_se_fosse_o_token():
    """Quem lê o banco tem o hash — e o hash não pode servir de senha."""
    db.init_db()
    email = 'reset-hash-nao-serve@example.com'
    if not db.buscar_usuario_email(email):
        db.criar_usuario(email, 'Reset Hash', 'senha123')

    token = db.criar_token_reset(email)
    assert db.validar_token_reset(db._hash_token_reset(token)) is None


# ── Segredo TOTP cifrado no banco ────────────────────────────────────────────

def _usuario_totp(email):
    db.init_db()
    u = db.buscar_usuario_email(email)
    if not u:
        db.criar_usuario(email, 'TOTP', 'senha123')
        u = db.buscar_usuario_email(email)
    return u['id']


def _segredo_cru(uid):
    return db._exec(f'SELECT totp_segredo FROM usuarios WHERE id={db._PH}',
                    (uid,), fetch='one')['totp_segredo']


def test_segredo_totp_nao_fica_em_claro_no_banco():
    """Um dump do banco não pode entregar o segundo fator de ninguém.

    Diferente de uma senha, o segredo TOTP não expira nem é trocado: quem o
    lê gera códigos válidos para sempre.
    """
    from services import totp as _totp

    uid = _usuario_totp('totp-cifrado@example.com')
    segredo = _totp.gerar_segredo()
    db.totp_guardar_segredo(uid, segredo)

    assert _segredo_cru(uid) != segredo, 'o segredo foi gravado em claro'
    assert db.totp_estado(uid)['segredo'] == segredo


def test_segredo_legado_em_claro_e_recifrado_na_leitura():
    """A base se corrige sozinha: quem já tinha 2FA não precisa reativar."""
    from services import totp as _totp

    uid = _usuario_totp('totp-legado@example.com')
    segredo = _totp.gerar_segredo()
    # Simula o que está gravado hoje em produção: base32 puro.
    db._exec(f'UPDATE usuarios SET totp_segredo={db._PH} WHERE id={db._PH}',
             (segredo, uid), commit=True)
    assert _segredo_cru(uid) == segredo

    assert db.totp_estado(uid)['segredo'] == segredo   # continua funcionando
    assert _segredo_cru(uid) != segredo                # e já subiu cifrado
    assert db.totp_estado(uid)['segredo'] == segredo   # e segue legível


def test_chave_trocada_derruba_para_o_backup_sem_trancar_a_conta(monkeypatch):
    """SECRET_KEY rotacionada sem TOTP_CHAVE não pode virar bloqueio total.

    O segredo fica ilegível de propósito — mas os códigos de backup são hash
    próprio e continuam valendo, então o usuário entra e reativa o 2FA.
    Silenciar seria burlar o 2FA; estourar trancaria também o backup.
    """
    from services import cripto_segredo as cripto
    from services import totp as _totp

    uid = _usuario_totp('totp-chave-trocada@example.com')
    db.totp_guardar_segredo(uid, _totp.gerar_segredo())

    monkeypatch.setenv('TOTP_CHAVE', cripto.Fernet.generate_key().decode())
    est = db.totp_estado(uid)

    assert est['segredo'] is None
    assert _totp.verificar(est['segredo'], '123456') is None


# ── Rotas caras têm limite ───────────────────────────────────────────────────

ROTAS_QUE_PRECISAM_DE_LIMITE = [
    '/api/shap',                  # pico de ~460 MB derruba o worker
    '/api/narrativa',             # Groq: abuso vira conta paga
    '/api/chat',                  # Groq
    '/api/ler-pdf',               # OCR
    '/api/fichas/importar',       # OCR em lote
    '/api/ler-planilha',
    '/api/importar-ficha-excel',
    '/api/parecer/pdf',
    '/api/parse-text',
    '/api/cenario',
    '/api/estimativa-valor',
    '/api/reconciliacao',
]


@pytest.mark.parametrize('rota', ROTAS_QUE_PRECISAM_DE_LIMITE)
def test_rota_cara_tem_rate_limit(rota):
    """Sem limite, um usuário logado em laço tira o app do ar para todos."""
    from services.rate_limit import limiter

    endpoints = {r.endpoint for r in app.url_map.iter_rules() if r.rule == rota}
    assert endpoints, f'rota {rota} não existe mais — atualize a lista'

    # O flask-limiter indexa os limites decorados por "modulo.qualname" da
    # view, não pelo nome do endpoint — daí a comparação por sufixo.
    limitados = set(limiter.limit_manager._decorated_limits)
    assert any(chave.endswith(f'.{ep}') for ep in endpoints for chave in limitados), \
        f'{rota} está sem @limiter.limit'


# ── O CSRF não pode barrar a própria entrada ─────────────────────────────────
#
# Regressão que chegou a produção: `login_user(..., remember=True)` faz quem já
# entrou uma vez voltar ao site AUTENTICADO. Se essa pessoa abre /login e manda
# o formulário de novo, a checagem de CSRF via — e o formulário de login não
# tem token, nem faz sentido ter. Resultado: 403 de página inteira no login.
#
# O CSRF existe para impedir que um site de terceiros dispare uma AÇÃO em nome
# de quem está logado. No login, no 2FA e na redefinição de senha não há ação a
# forjar: cada um tem credencial própria.

def _usuario_para_login(email):
    db.init_db()
    if not db.buscar_usuario_email(email):
        db.criar_usuario(email, 'Login', 'senha123')
    app.config['TESTING'] = True
    return app.test_client()


def test_quem_ja_esta_logado_consegue_reenviar_o_login():
    email = 'csrf-relogin@example.com'
    c = _usuario_para_login(email)
    c.csrf = False   # o formulário de login não manda token, e não deve mesmo
    assert c.post('/login', data={'email': email, 'senha': 'senha123'}).status_code == 302
    # segunda vez, agora já autenticado — era aqui que dava 403
    assert c.post('/login', data={'email': email, 'senha': 'senha123'}).status_code == 302


def test_as_rotas_de_recuperacao_de_senha_nao_pedem_csrf():
    email = 'csrf-recuperacao@example.com'
    c = _usuario_para_login(email)
    c.csrf = False
    c.post('/login', data={'email': email, 'senha': 'senha123'})
    assert c.post('/api/esqueci-senha', json={'email': email}).status_code != 403
    # 400 por token inválido é resposta da rota; 403 seria o CSRF barrando
    assert c.post('/api/redefinir-senha',
                  json={'token': 'x', 'senha': 'y'}).status_code != 403


def test_a_isencao_nao_vaza_para_o_resto_do_app():
    """Só as entradas pré-autenticação; nenhuma rota de ação."""
    import app as app_module
    assert app_module._CSRF_ISENTOS == {
        'login', 'login_2fa', 'cadastro',
        'api_esqueci_senha', 'api_redefinir_senha',
        'whatsapp_verificacao', 'whatsapp_webhook',
    }


def test_rota_de_acao_continua_exigindo_csrf():
    """A correção não pode ter reaberto o buraco que ela veio fechar."""
    c = _cliente_logado()
    c.csrf = False
    assert c.post('/api/fazendas', json={'nome': 'Forjada'}).status_code == 403
