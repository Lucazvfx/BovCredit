"""
Plataforma de Análise de Crédito Pecuário — Servidor Flask
"""
import logging
import os
import re
import io
import tempfile
import subprocess
from functools import wraps

from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, send_from_directory, send_file, session, abort
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from apscheduler.schedulers.background import BackgroundScheduler

from ml_engine import (
    treinar_modelo, classificar, calcular_indicadores,
    simular_cenario, carregar_modelo, CENARIOS,
    avaliar_benchmarks, extrair_indicadores_benchmark, calcular_breakeven_simples,
    explicar_shap, TIPOS,
)
import database as db

# Importações do PDF parsers (evitamos sobrescrever com definições locais)
from pdf_parsers import (
    parsear_idaron, parsear_indea, parsear_declaracao_idaron,
    parsear_generico,
    parsear_iagro_ms, parsear_aged_ma, parsear_agrodefesa_go,
    parsear_adapec_to, parsear_adepara_pa,
    parsear_go_declaracao_web,
    ORIGENS_GENERICAS, ORIGENS_INDEA,
)

from services.importar_excel import parsear_ficha_excel

from scraper import obter_precos_arroba, _session_com_retry, _HEADERS as _SCRAPER_HEADERS

from parsers.composicao_rebanho import ler_template
from services.consistencia_rebanho import analisar_consistencia, analisar_consistencia_historica
from services.benchmarks_nacionais import avaliar_nacional, avaliar_zootecnico, CICLO_CATEGORIAS
from services.parecer_credito import montar_parecer
from services.parecer_pdf import gerar_pdf_parecer
from services.pesos_rebanho import arrobas_categorias
from services.custos_desembolso import (
    custo_arroba_de_desembolso, COMPONENTES, custo_arroba_padrao,
)
from services.reconciliacao import reconciliar
from services.fluxo_caixa_gep import valor_rebanho_gep, calcular_fluxo_gep
from services.garantia import avaliar_garantia
from services.precos_regionais import aplicar as aplicar_preco_regional
from services.endividamento import consolidar as consolidar_endividamento
from services.benchmarks_nacionais import avaliar_coe as _avaliar_coe
from services.groq_narrativa import (
    gerar_narrativa as _gerar_narrativa_groq,
    _feature_ativa as _narrativa_ativa,
)

# Narrativa IA: por padrão assíncrona (endpoint /api/narrativa), para não
# somar até 20s de latência do Groq ao parecer. NARRATIVA_INLINE=1 restaura
# o comportamento bloqueante anterior.
_NARRATIVA_INLINE = os.environ.get('NARRATIVA_INLINE', '0') == '1'

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20 MB

# ── Session cookie hardening ──────────────────────────────────────────────────
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = bool(os.environ.get('RAILWAY_ENVIRONMENT'))

# ── Security headers via after_request ───────────────────────────────────────
@app.after_request
def _set_security_headers(response):
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    return response

_secret_key = os.environ.get('SECRET_KEY')
if not _secret_key:
    if os.environ.get('FLASK_ENV') == 'production' or os.environ.get('RAILWAY_ENVIRONMENT'):
        raise RuntimeError('SECRET_KEY não definida em produção — defina a variável de ambiente.')
    _secret_key = 'boviml-dev-secret-local'
app.secret_key = _secret_key

# ── CSRF protection para rotas admin ─────────────────────────────────────────
def _csrf_token() -> str:
    if 'csrf_token' not in session:
        session['csrf_token'] = _secrets.token_hex(32)
    return session['csrf_token']

app.jinja_env.globals['csrf_token'] = _csrf_token

@app.before_request
def _verificar_csrf_admin():
    if request.method == 'POST' and request.path.startswith('/admin'):
        token = request.form.get('csrf_token', '')
        if not token or not _secrets.compare_digest(token, session.get('csrf_token', '')):
            abort(403)

# ── Erros: resposta útil em vez de página HTML muda ──────────────────────────
# O frontend consome JSON. Quando uma rota /api quebrava, o Flask devolvia a
# página HTML padrão de 500, o res.json() do navegador lançava e a tela ficava
# muda — o usuário via o spinner sumir, sem resultado e sem mensagem, e não
# tinha o que reportar.
#
# Agora todo erro em /api vira JSON com um identificador curto, que também vai
# para o log do servidor: o usuário informa a referência e ela localiza o
# traceback exato.
import uuid as _uuid
from werkzeug.exceptions import HTTPException as _HTTPException


@app.errorhandler(Exception)
def _erro_json(e):
    if isinstance(e, _HTTPException) and not request.path.startswith('/api'):
        return e            # páginas seguem com o comportamento padrão do Flask

    if isinstance(e, _HTTPException):
        return jsonify({'erro': e.description or e.name,
                        'status': e.code}), e.code

    trace_id = _uuid.uuid4().hex[:8]
    logger.exception(f'[{trace_id}] erro não tratado em {request.method} {request.path}')
    if request.path.startswith('/api'):
        return jsonify({
            'erro': 'Erro interno ao processar a solicitação.',
            'trace_id': trace_id,
            'status': 500,
        }), 500
    raise e


# ── Rate limiting (proteção contra força bruta) ───────────────────────────────
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],          # sem limite global — só endpoints sensíveis
    storage_uri='memory://',
)

# ── Controle de acesso: administradores ───────────────────────────────────────
# Defina ADMIN_EMAILS no Railway (ex.: "voce@email.com"). Só admins acessam
# /admin, onde criam as contas dos usuários. O cadastro público fica desativado.
import secrets as _secrets

_ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.environ.get('ADMIN_EMAILS', '').split(',')
    if e.strip()
}


def is_admin(email: str) -> bool:
    """True se o e-mail é de um administrador."""
    return (email or '').strip().lower() in _ADMIN_EMAILS


def gerar_senha(n: int = 10) -> str:
    """Gera uma senha aleatória legível (sem caracteres ambíguos)."""
    alfabeto = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return ''.join(_secrets.choice(alfabeto) for _ in range(n))


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        if not is_admin(getattr(current_user, 'email', '')):
            return redirect(url_for('app_main'))
        return f(*args, **kwargs)
    return wrapper


def _resolver_empresa_ativa():
    """Empresa ativa da sessão; escolhe a primeira se ausente/inválida.
    Devolve None se o usuário não pertence a nenhuma empresa."""
    empresas = db.empresas_do_usuario(current_user.id)
    if not empresas:
        return None
    ativa = session.get('empresa_ativa_id')
    if ativa and any(e['id'] == ativa for e in empresas):
        return ativa
    nova_ativa = empresas[0]['id']
    session['empresa_ativa_id'] = nova_ativa
    return nova_ativa


def _empresa_ativa_ou_400():
    """Para endpoints JSON: devolve (empresa_id, None) ou (None, response_erro)."""
    eid = _resolver_empresa_ativa()
    if eid is None:
        return None, (jsonify({'erro': 'Usuário sem empresa vinculada'}), 400)
    return eid, None


def garantir_admins():
    """Provisiona as contas admin no start (resolve o ovo-e-galinha do acesso).

    Para cada e-mail em ADMIN_EMAILS: se não existir conta, cria uma com a
    senha de ADMIN_SENHA_INICIAL (ou uma gerada, logada uma vez). Se a conta já
    existir e ADMIN_RESET_SENHA estiver ligado, redefine a senha para
    ADMIN_SENHA_INICIAL — lever de recuperação quando você esquece a senha.
    """
    senha_inicial = os.environ.get('ADMIN_SENHA_INICIAL', '').strip()
    resetar = os.environ.get('ADMIN_RESET_SENHA', '').strip().lower() in (
        '1', 'true', 'yes', 'sim')
    for email in _ADMIN_EMAILS:
        existente = db.buscar_usuario_email(email)
        if existente is None:
            senha = senha_inicial or gerar_senha()
            db.criar_usuario(email, email.split('@')[0], senha)
            origem_label = 'ADMIN_SENHA_INICIAL' if senha_inicial else 'gerada automaticamente'
            logger.warning(f"[ADMIN] Conta criada para {email} (senha {origem_label} — anote antes do próximo restart)")
        elif resetar and senha_inicial:
            db.resetar_senha(email, senha_inicial)
            logger.warning(f"[ADMIN] Senha redefinida para {email} (ADMIN_RESET_SENHA).")

# ── Flask-Login ──────────────────────────────────────────────────────────────
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Faça login para acessar o sistema.'

class User(UserMixin):
    def __init__(self, data: dict):
        self.id    = data['id']
        self.email = data['email']
        self.nome  = data['nome']
        self.plano = data.get('plano', 'free')

@login_manager.user_loader
def load_user(user_id):
    u = db.buscar_usuario_id(int(user_id))
    return User(u) if u else None

# ── Startup: carrega modelo do disco ou treina do zero ──────────────────────
_saved = carregar_modelo()
if _saved:
    stats = _saved
    logger.info(f"✅ Modelo carregado do disco | Acurácia: {stats['accuracy_mean']*100:.1f}% | Amostras: {stats['n_samples']}")
else:
    logger.info("🧠 Treinando modelo ML (primeira execução)...")
    stats = treinar_modelo()
    logger.info(f"✅ Modelo treinado | Acurácia CV: {stats['accuracy_mean']*100:.1f}% ± {stats['accuracy_std']*100:.1f}% | Amostras: {stats['n_samples']}")

db.init_db()
logger.info("🗃️  Banco SQLite inicializado.")
garantir_admins()

# ── Automação: Cotações Diárias (Scraper) ────────────────────────────────────
def rotina_diaria_cotacoes():
    """Função executada em background para atualizar preços da arroba."""
    logger.info("📈 [Scraper] A iniciar a busca automática de cotações...")
    try:
        precos = obter_precos_arroba()
        if precos.get('boi', 0) > 0 or precos.get('vaca', 0) > 0:
            db.guardar_cotacao_diaria(precos)
            _invalidar_cache_cotacoes()
            logger.info("✅ [Scraper] Cotações atualizadas no banco de dados.")
        else:
            logger.warning("⚠️ [Scraper] Cotações retornaram zero, não salvas.")
    except Exception as e:
        logger.error(f"❌ [Scraper] Erro na rotina: {e}", exc_info=True)

# Em modo debug, o Reloader do Flask inicia o processo duas vezes — só inicia o
# scheduler no processo filho (WERKZEUG_RUN_MAIN=true) ou fora do debug.
if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
    import threading
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(rotina_diaria_cotacoes, 'cron', hour=8, minute=0)
    scheduler.start()
    threading.Thread(target=rotina_diaria_cotacoes, daemon=True).start()

# ── Auth routes ─────────────────────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute; 30 per hour")
def login():
    if current_user.is_authenticated:
        return redirect(url_for('app_main'))
    erro = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        senha = request.form.get('senha', '').strip()
        u = db.verificar_senha(email, senha)
        if u:
            login_user(User(u), remember=True)
            return redirect(url_for('app_main'))
        logger.warning(f'[LOGIN] Falha de autenticação para e-mail: {email!r}')
        erro = 'E-mail ou senha incorretos.'
    return render_template('login.html', erro=erro)

@app.route('/esqueci-senha', methods=['GET'])
def esqueci_senha():
    return render_template('esqueci_senha.html')


@app.route('/api/esqueci-senha', methods=['POST'])
@limiter.limit("5 per hour")
def api_esqueci_senha():
    from services.email_service import enviar_reset_senha, smtp_configurado
    dados = request.get_json(force=True, silent=True) or {}
    email = (dados.get('email') or '').strip().lower()
    if not email or '@' not in email:
        return jsonify({'erro': 'Informe um e-mail válido.'}), 400

    usuario = db.buscar_usuario_email(email)
    # Não revela se o e-mail existe ou não (evita enumeração)
    if usuario:
        token = db.criar_token_reset(email)
        if smtp_configurado():
            enviar_reset_senha(email, usuario.get('nome', email), token)
        else:
            # Sem SMTP: loga o link para o admin copiar manualmente
            app_url = os.environ.get('APP_URL', request.host_url.rstrip('/'))
            link = f'{app_url}/redefinir-senha?token={token}'
            logger.warning(f'[RESET] SMTP não configurado. Token de reset gerado para {email} (acesse /admin para gerenciar senhas)')

    return jsonify({'ok': True, 'mensagem': 'Se o e-mail estiver cadastrado, você receberá as instruções em breve.'})


@app.route('/redefinir-senha', methods=['GET'])
def redefinir_senha():
    token = request.args.get('token', '').strip()
    if not token:
        return render_template('esqueci_senha.html', erro='Link inválido. Solicite um novo.')
    email = db.validar_token_reset(token)
    if not email:
        return render_template('esqueci_senha.html', erro='Link expirado ou já utilizado. Solicite um novo.')
    return render_template('redefinir_senha.html', token=token)


@app.route('/api/redefinir-senha', methods=['POST'])
def api_redefinir_senha():
    dados = request.get_json(force=True, silent=True) or {}
    token = (dados.get('token') or '').strip()
    nova = (dados.get('nova_senha') or '').strip()
    confirma = (dados.get('confirmar_senha') or '').strip()

    if not token:
        return jsonify({'erro': 'Token ausente.'}), 400
    if len(nova) < 8:
        return jsonify({'erro': 'A senha deve ter ao menos 8 caracteres.'}), 400
    if nova != confirma:
        return jsonify({'erro': 'As senhas não coincidem.'}), 400

    email = db.validar_token_reset(token)
    if not email:
        return jsonify({'erro': 'Link expirado ou já utilizado. Solicite um novo.'}), 400

    db.resetar_senha(email, nova)
    db.consumir_token_reset(token)
    return jsonify({'ok': True, 'mensagem': 'Senha redefinida com sucesso. Faça login.'})


@app.route('/privacidade')
def privacidade():
    return render_template('privacidade.html')

@app.route('/termos')
def termos():
    return render_template('termos.html')

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    # Cadastro público desativado: apenas administradores criam contas em /admin.
    return render_template(
        'login.html',
        erro='O cadastro é feito pelo administrador. Solicite seu acesso.'
    ), 403


# ── Administração de usuários ─────────────────────────────────────────────────
@app.route('/admin')
@admin_required
def admin():
    return render_template(
        'admin.html',
        usuarios=db.listar_usuarios(),
        usuario=current_user,
        nova_conta=None,
        empresas=db._exec('SELECT * FROM empresas ORDER BY nome', fetch='all') or [],
        membros=db._exec('''SELECT m.empresa_id, m.user_id, e.nome as empresa_nome,
                            u.email as user_email FROM empresa_membros m
                            JOIN empresas e ON e.id=m.empresa_id
                            JOIN usuarios u ON u.id=m.user_id ORDER BY e.nome''', fetch='all') or [],
    )

@app.route('/admin/empresas/criar', methods=['POST'])
@admin_required
def admin_criar_empresa():
    nome = (request.form.get('nome') or '').strip()
    if nome:
        db._exec(f"INSERT INTO empresas (nome) VALUES ({db._PH})", (nome,), commit=True)
    return redirect(url_for('admin'))

@app.route('/admin/empresas/vincular', methods=['POST'])
@admin_required
def admin_vincular_empresa():
    user_id = request.form.get('user_id')
    empresa_id = request.form.get('empresa_id')
    if user_id and empresa_id and not db.usuario_pertence_a_empresa(int(user_id), int(empresa_id)):
        db._exec(f"INSERT INTO empresa_membros (empresa_id, user_id) VALUES ({db._PH},{db._PH})",
                 (int(empresa_id), int(user_id)), commit=True)
    return redirect(url_for('admin'))

@app.route('/admin/empresas/desvincular', methods=['POST'])
@admin_required
def admin_desvincular_empresa():
    user_id = request.form.get('user_id')
    empresa_id = request.form.get('empresa_id')
    if user_id and empresa_id:
        db._exec(f"DELETE FROM empresa_membros WHERE user_id={db._PH} AND empresa_id={db._PH}",
                 (int(user_id), int(empresa_id)), commit=True)
    return redirect(url_for('admin'))


@app.route('/admin/criar', methods=['POST'])
@admin_required
def admin_criar():
    nome  = request.form.get('nome', '').strip()
    email = request.form.get('email', '').strip().lower()
    erro = None
    nova_conta = None
    if not nome or not email:
        erro = 'Preencha nome e e-mail.'
    elif db.buscar_usuario_email(email):
        erro = 'E-mail já cadastrado.'
    else:
        senha = gerar_senha()
        db.criar_usuario(email, nome, senha)
        nova_conta = {'nome': nome, 'email': email, 'senha': senha}
    return render_template(
        'admin.html',
        usuarios=db.listar_usuarios(),
        usuario=current_user,
        nova_conta=nova_conta,
        erro=erro,
        empresas=db._exec('SELECT * FROM empresas ORDER BY nome', fetch='all') or [],
        membros=db._exec('''SELECT m.empresa_id, m.user_id, e.nome as empresa_nome,
                            u.email as user_email FROM empresa_membros m
                            JOIN empresas e ON e.id=m.empresa_id
                            JOIN usuarios u ON u.id=m.user_id ORDER BY e.nome''', fetch='all') or [],
    )


@app.route('/admin/remover/<int:uid>', methods=['POST'])
@admin_required
def admin_remover(uid):
    alvo = db.buscar_usuario_id(uid)
    if alvo and not is_admin(alvo['email']):
        db.remover_usuario(uid)
    return redirect(url_for('admin'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ── Empresa ativa ────────────────────────────────────────────────────────────
@app.route('/api/empresa/ativa', methods=['GET'])
@login_required
def api_empresa_ativa_get():
    empresas = db.empresas_do_usuario(current_user.id)
    ativa_id = _resolver_empresa_ativa()
    return jsonify({'empresas': empresas, 'ativa_id': ativa_id})

@app.route('/api/empresa/ativa', methods=['POST'])
@login_required
def api_empresa_ativa_post():
    empresa_id = (request.json or {}).get('empresa_id')
    if not isinstance(empresa_id, int):
        return jsonify({'erro': 'empresa_id inválido'}), 400
    if not db.usuario_pertence_a_empresa(current_user.id, empresa_id):
        return jsonify({'erro': 'Você não pertence a essa empresa'}), 403
    session['empresa_ativa_id'] = empresa_id
    return jsonify({'ok': True})

# ── Fazendas ─────────────────────────────────────────────────────────────────
@app.route('/api/fazendas', methods=['GET'])
@login_required
def api_listar_fazendas():
    empresa_id, erro = _empresa_ativa_ou_400()
    if erro:
        return erro
    return jsonify({'fazendas': db.listar_fazendas(empresa_id)})

@app.route('/api/fazendas', methods=['POST'])
@login_required
def api_criar_fazenda():
    empresa_id, erro = _empresa_ativa_ou_400()
    if erro:
        return erro
    data = request.json
    nome = (data.get('nome') or '').strip()
    if not nome:
        return jsonify({'erro': 'Nome obrigatório'}), 400
    fid = db.criar_fazenda(
        nome=nome,
        proprietario=data.get('proprietario', ''),
        municipio=data.get('municipio', ''),
        estado=data.get('estado', ''),
        empresa_id=empresa_id,
        criado_por=current_user.id,
    )
    return jsonify({'ok': True, 'id': fid})

@app.route('/api/fazendas/<int:fid>/historico', methods=['GET'])
@login_required
def api_historico_fazenda(fid):
    empresa_id, erro = _empresa_ativa_ou_400()
    if erro:
        return erro
    f = db.buscar_fazenda(fid, empresa_id)
    if not f:
        return jsonify({'erro': 'Fazenda não encontrada'}), 404
    hist = db.historico_fazenda(fid)
    return jsonify({'fazenda': dict(f), 'historico': hist})

@app.route('/api/fazendas/<int:fid>/pareceres', methods=['GET'])
@login_required
def api_fazenda_pareceres(fid):
    empresa_id, erro = _empresa_ativa_ou_400()
    if erro:
        return erro
    if not db.buscar_fazenda(fid, empresa_id):
        return jsonify({'erro': 'Fazenda não encontrada'}), 404
    itens = db.listar_pareceres(fazenda_id=fid)
    return jsonify({'pareceres': itens})

@app.route('/api/empresa/perfil', methods=['GET', 'POST'])
@login_required
def api_empresa_perfil():
    empresa_id, erro = _empresa_ativa_ou_400()
    if erro:
        return erro
    if request.method == 'POST':
        data = request.json or {}
        db.atualizar_perfil_empresa(
            empresa_id, data.get('nome_consultoria', ''), data.get('logo_base64', ''))
        return jsonify({'ok': True})
    e = db.buscar_empresa(empresa_id)
    return jsonify({
        'nome_consultoria': (e.get('nome') or '') if e else '',
        'logo_base64': (e.get('logo_base64') or '') if e else '',
    })

@app.route('/api/parecer/pdf', methods=['POST'])
@login_required
def api_parecer_pdf():
    parecer = (request.json or {}).get('parecer')
    if not parecer:
        return jsonify({'erro': 'parecer é obrigatório'}), 400
    empresa_id = _resolver_empresa_ativa()
    e = db.buscar_empresa(empresa_id) if empresa_id else None
    branding = {'nome_consultoria': e.get('nome') or '',
                'logo_base64': e.get('logo_base64') or ''} if e else None
    pdf_bytes = gerar_pdf_parecer(parecer, branding=branding)
    return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf',
                     as_attachment=True, download_name='parecer_credito.pdf')

# ── Landing page pública ───────────────────────────────────────────────────────
@app.route('/')
def landing():
    if current_user.is_authenticated:
        return redirect(url_for('app_main'))
    return render_template('landing.html')

# ── App principal ─────────────────────────────────────────────────────────────
@app.route('/app')
@login_required
def app_main():
    empresa_id = _resolver_empresa_ativa()
    fazendas = db.listar_fazendas(empresa_id) if empresa_id else []
    cotacoes_dia = db.obter_cotacoes_atuais()
    return render_template('index.html', model_stats=stats, cenarios=CENARIOS,
                           usuario=current_user, fazendas=fazendas, cotacoes=cotacoes_dia,
                           eh_admin=is_admin(current_user.email))

@app.route('/api/classificar', methods=['POST'])
@login_required
def api_classificar():
    data = request.json
    v = data.get('valores', [])
    if len(v) != 10 or not all(isinstance(x, (int, float)) and x >= 0 for x in v) or sum(v) < 10:
        return jsonify({'erro': 'Envie 10 valores >= 0 (fêmeas e machos por faixa) com total >= 10'}), 400

    kwargs = {}
    if 'taxa_natalidade' in data:
        kwargs['taxa_natalidade'] = float(data['taxa_natalidade'])
    if 'bois_vendidos' in data:
        kwargs['bois_vendidos'] = float(data['bois_vendidos'])
    if 'bezerros_vendidos' in data:
        kwargs['bezerros_vendidos'] = float(data['bezerros_vendidos'])

    result = classificar(v, **kwargs)
    ind    = calcular_indicadores(v)

    # Indicadores comparáveis a benchmarks regionais (GEP Araguaia / Rondônia):
    # usa o que o usuário informou (mortalidade_pct, desmama_pct,
    # rend_carcaca_pct, ganho_peso_kg_dia, desfrute_pct) e completa o
    # resto com defaults regionais ou com o que já foi calculado do rebanho.
    ind_bench  = extrair_indicadores_benchmark(v, data)
    benchmarks = avaliar_benchmarks(result['tipo'], ind_bench)
    breakeven  = calcular_breakeven_simples(v, result['tipo'])

    # Painel de benchmarks NACIONAIS (multi-fonte + financeiro): confronta os
    # indicadores contra cada fonte institucional (Embrapa, Scot, CEPEA-USP,
    # ABCZ, ASBIA) e contra o desembolso de referência (Inttegra 2025).
    def _opt_float(x):
        try:
            return float(x) if x not in (None, '') else None
        except (TypeError, ValueError):
            return None
    painel_nacional = avaliar_nacional(result['tipo'], {
        'prenhez':    _opt_float(data.get('taxa_prenhez_pct')),
        'natalidade': ind_bench.get('natalidade'),
        'desfrute':   ind_bench.get('desfrute'),
        'desembolso': _opt_float(data.get('desembolso_cab_mes')),
    })

    # Avaliação zootécnica EMBRAPA CNPGC
    _ind_zoo = {}
    if ind_bench.get('natalidade') is not None:
        _ind_zoo['natalidade_pct'] = ind_bench['natalidade']
    if ind_bench.get('desfrute') is not None:
        _ind_zoo['desfrute_pct'] = ind_bench['desfrute']
    if _opt_float(data.get('mortalidade_pct')) is not None:
        _ind_zoo['mortalidade_bezerros_pct'] = _opt_float(data.get('mortalidade_pct'))
    if _opt_float(data.get('lotacao_ua_ha')) is not None:
        _ind_zoo['lotacao_ua_ha'] = _opt_float(data.get('lotacao_ua_ha'))
    if _opt_float(data.get('gmd_g_dia')) is not None:
        _ind_zoo['gmd_g_dia'] = _opt_float(data.get('gmd_g_dia'))
    avaliacao_embrapa = avaliar_zootecnico(result['tipo'], _ind_zoo)
    ciclo_info = CICLO_CATEGORIAS.get(result['tipo'], {})

    # Salvar automaticamente no BD para futuros retreinamentos
    fazenda   = data.get('fazenda', '')
    municipio = data.get('municipio', '')
    nat_pct   = float(data.get('taxa_natalidade', 0.75)) * 100
    registro_id = db.salvar(
        valores=v,
        class_ml=result['classificacao'],
        confianca=result['confianca'],
        fazenda=fazenda,
        municipio=municipio,
        nat_pct=nat_pct,
    )

    # Consistência do rebanho declarado (diferencial de análise de crédito):
    # roda também no fluxo principal, não só na importação de PDF.
    consistencia = analisar_consistencia(v)

    # Consistência histórica: compara com a declaração anterior da mesma fazenda.
    fazenda_id_hist = data.get('fazenda_id')
    if fazenda_id_hist:
        hist = db.historico_fazenda(int(fazenda_id_hist), limit=1)
        if hist and hist[0].get('valores'):
            flags_hist = analisar_consistencia_historica(v, hist[0]['valores'])
            if flags_hist:
                consistencia['flags'] = flags_hist + consistencia['flags']
                erros_hist = sum(1 for f in flags_hist if f['severidade'] == 'erro')
                alertas_hist = sum(1 for f in flags_hist if f['severidade'] == 'alerta')
                consistencia['resumo']['erros'] += erros_hist
                consistencia['resumo']['alertas'] += alertas_hist
                penalidade = erros_hist * 25 + alertas_hist * 8
                consistencia['score_consistencia'] = max(0, consistencia['score_consistencia'] - penalidade)

    # Custo real por componentes (desembolso R$/cab/mês) → custo_arroba exato.
    # Se não vierem componentes, usa custo_arroba do campo único; e se o
    # analista também não informar isso, o padrão segue a MODALIDADE detectada.
    #
    # Antes o default era 119 R$/@ para qualquer ciclo — o valor do
    # CICLO_COMPLETO, que inclui terminação e é intensivo em ração. Aplicado a
    # uma cria extensiva (GEP: R$90,88/cab/mês contra R$119,14) superestimava
    # o custo em ~30% e levava rebanhos saudáveis a caixa negativo.
    _custo_padrao_ciclo = custo_arroba_padrao(result.get('tipo', 'CICLO_COMPLETO'))
    custo_arroba = float(data.get('custo_arroba') or _custo_padrao_ciclo)
    custo_desembolso = None
    componentes = data.get('custo_componentes') or {}
    desembolso_cab_mes = sum(float(componentes.get(k, 0) or 0) for k, _ in COMPONENTES)
    if desembolso_cab_mes > 0:
        femeas_024 = float(v[0] + v[2] + v[4])
        machos_024 = float(v[1] + v[3] + v[5])
        matrizes   = float(v[6] + v[8])
        bois       = float(v[7] + v[9])
        arrobas_rebanho = arrobas_categorias(
            matrizes=matrizes, bois=bois, jovens_f=femeas_024, jovens_m=machos_024)
        total_cabecas = int(sum(v))
        custo_arroba = custo_arroba_de_desembolso(
            desembolso_cab_mes, arrobas_rebanho, total_cabecas)
        custo_desembolso = {
            'componentes': {k: float(componentes.get(k, 0) or 0) for k, _ in COMPONENTES},
            'desembolso_cab_mes': round(desembolso_cab_mes, 2),
            'custo_arroba': round(custo_arroba, 2),
            'peso_medio_arroba': round(arrobas_rebanho / max(total_cabecas, 1), 2),
        }

    # Preços por categoria (cotação do dia): request → banco → None (usa arroba).
    _cot = db.obter_cotacoes_atuais() or {}
    _preco_digitado = set()
    def _preco(chave):
        do_request = float(data.get(chave) or 0)
        if do_request > 0:
            _preco_digitado.add(chave)
            return do_request
        v_ = float(_cot.get(chave.replace('preco_', '')) or 0)
        return v_ if v_ > 0 else None

    _precos_nac = {c: _preco(c) for c in
                   ('preco_boi', 'preco_vaca', 'preco_bezerra', 'preco_bezerro')}

    # ── Preço da praça ───────────────────────────────────────────────────────
    # O indicador CEPEA/ESALQ é praça de São Paulo, e o sistema o aplicava
    # igual no Brasil inteiro. Um LTV com preço paulista numa fazenda de RO
    # está errado por construção — e é o LTV que decide se a garantia cobre.
    #
    # Só a cotação nacional recebe o diferencial: preço digitado pelo analista
    # já é o da praça dele, e ajustar de novo descontaria duas vezes.
    #
    # A tela preenche os campos de cotação com o indicador nacional e os envia,
    # então "veio no request" NÃO significa "digitado". Quando o cliente manda
    # `precos_manuais`, ela é a autoridade sobre o que o analista alterou de
    # fato; sem ela, mantém-se o comportamento antigo (preço enviado = manual),
    # que é o certo para quem chama a API direto.
    if isinstance(data.get('precos_manuais'), list):
        _preco_digitado = {str(k) for k in data['precos_manuais']}
    _reg = aplicar_preco_regional(
        _precos_nac,
        municipio=municipio,
        uf=data.get('uf'),
        ajustaveis=set(_precos_nac) - _preco_digitado,
    )
    _precos_nac = _reg['precos']
    precos_regional = _reg['regional']

    preco_boi     = _precos_nac['preco_boi']
    preco_vaca    = _precos_nac['preco_vaca']
    preco_bezerra = _precos_nac['preco_bezerra']
    preco_bezerro = _precos_nac['preco_bezerro']

    # Geração de caixa recorrente: resultado do ano 1 no cenário conservador,
    # dentro do ciclo detectado (número mais conservador e recorrente).
    def _custo_fase(chave):
        v_ = float(data.get(chave) or 0)
        return v_ if v_ > 0 else None
    _cx = simular_cenario(
        v, 'conservador', ciclo=result['tipo'],
        preco_arroba=preco_boi or float(data.get('preco', 320)),
        custo_arroba=custo_arroba,
        custo_arroba_cria=_custo_fase('custo_arroba_cria'),
        custo_arroba_recria=_custo_fase('custo_arroba_recria'),
        custo_arroba_engorda=_custo_fase('custo_arroba_engorda'),
        preco_boi_arr=preco_boi, preco_vaca_arr=preco_vaca,
        preco_bezerra_cab=preco_bezerra, preco_bezerro_cab=preco_bezerro)
    geracao_caixa_anual = _cx['anos'][0]['resultado']

    # ── Desfrute PROJETADO pela própria simulação ────────────────────────────
    # O sistema calculava o desfrute implicitamente (pelas vendas do ano 1) mas
    # nunca o confrontava com a própria referência: `desfrute` só entrava no
    # painel se o analista o digitasse à mão. Uma projeção que vende o dobro do
    # normal passava sem alarme e inflava o DSCR.
    #
    # Aqui ele é calculado e devolvido ao painel de benchmarks, que já sabe
    # avaliar por modalidade (CRIA 18–30%, CICLO_COMPLETO 20–40%, etc.).
    _ano1_desf   = _cx['anos'][0]
    _vend_ano1   = (_ano1_desf.get('vendidos', 0)
                    + _ano1_desf.get('matrizes_descartadas', 0))
    desfrute_projetado = round(_vend_ano1 / max(sum(v), 1) * 100, 1)
    if ind_bench.get('desfrute') is None:
        ind_bench['desfrute'] = desfrute_projetado
        # Reavalia com o desfrute preenchido — as duas chamadas abaixo rodaram
        # antes da simulação existir e não tinham como conhecê-lo.
        benchmarks = avaliar_benchmarks(result['tipo'], ind_bench)
        painel_nacional = avaliar_nacional(result['tipo'], {
            'prenhez':    _opt_float(data.get('taxa_prenhez_pct')),
            'natalidade': ind_bench.get('natalidade'),
            'desfrute':   desfrute_projetado,
            'desembolso': _opt_float(data.get('desembolso_cab_mes')),
        })

    # ── Fluxo de caixa completo — metodologia GEP Araguaia ──────────────────
    # Calcula variação de estoque do rebanho (ativo que valoriza ou deprecia).
    # Diferencial: nenhum sistema de crédito rural calcula isso automaticamente.
    _va = [float(x) for x in v]
    _preco_boi_ref = preco_boi or float(data.get('preco', 320))
    _val_ini = valor_rebanho_gep(
        matrizes = _va[6] + _va[8],   # f25F + facF
        bois     = _va[7] + _va[9],   # f25M + facM
        novilhas = _va[4],             # f13F  (9.33@ × pv)
        garrotes = _va[5],             # f13M  (10.67@ × pb)
        bezerras = _va[0] + _va[2],   # f00F + f05F (R$/cab)
        bezerros = _va[1] + _va[3],   # f00M + f05M (R$/cab)
        preco_boi        = _preco_boi_ref,
        preco_vaca       = preco_vaca,
        preco_bezerra_cab = preco_bezerra,
        preco_bezerro_cab = preco_bezerro,
    )
    _ano1 = _cx['anos'][0]
    _val_fim = valor_rebanho_gep(
        matrizes = float(_ano1['matrizes']),
        bois     = _ano1.get('bois_fim', _va[7] + _va[9]),
        jovens_f = float(_ano1.get('jovens_f_fim', 0)),
        jovens_m = float(_ano1.get('jovens_m_fim', 0)),
        preco_boi  = _preco_boi_ref,
        preco_vaca = preco_vaca,
    )
    # A variação de estoque precisa comparar as duas pontas pelo MESMO método.
    # _val_ini é granular (preço por categoria) e _val_fim é agregado (peso médio
    # dos jovens) — a diferença de método sozinha cria ~4% de variação fantasma.
    # Para a variação, revaloriza a abertura no formato agregado.
    _val_ini_cmp = valor_rebanho_gep(
        matrizes = _va[6] + _va[8],
        bois     = _va[7] + _va[9],
        jovens_f = _va[0] + _va[2] + _va[4],
        jovens_m = _va[1] + _va[3] + _va[5],
        preco_boi  = _preco_boi_ref,
        preco_vaca = preco_vaca,
    )
    # Reposição de reprodutores: touros renovados × preço por cabeça
    # Touro reprodutor ≈ 1.5× valor do boi comercial (benchmark mercado RO/MT)
    _matrizes_ini   = _va[6] + _va[8]
    _prop_boi       = float(data.get('propboi', 30))
    _renov_boi_pct  = float(data.get('renovboi', 20)) / 100
    _touros_nec     = max(_matrizes_ini / max(_prop_boi, 1), 0)
    _touros_renovados = _touros_nec * _renov_boi_pct
    _fator_touro    = float(data.get('fator_touro', 1.5))  # multiplier s/ boi comercial
    _peso_touro_arr = 20.53  # arrobas — mesmo do CATEGORIAS_GEP['boi']
    _preco_touro_cab = _preco_boi_ref * _peso_touro_arr * _fator_touro
    _reposicao_reprodutores = round(_touros_renovados * _preco_touro_cab, 2)
    # DSCR calculado após deduzir reposição de reprodutores (saída real de caixa)
    geracao_caixa_anual -= _reposicao_reprodutores

    # Serviço da dívida para o fluxo GEP (mesma base do DSCR do parecer)
    _parcela_nova = 0.0
    if data.get('credito_valor') and data.get('prazo_meses') and data.get('juros_aa'):
        from services.parecer_credito import parcela_price
        _n = max(int(data.get('prazo_meses', 0)) - int(data.get('carencia_meses', 0) or 0), 0)
        _parcela_nova = parcela_price(
            float(data.get('credito_valor', 0)),
            float(data.get('juros_aa', 0)),
            _n,
        )

    # Endividamento existente: o campo único "dívidas mensais" passa a aceitar
    # um inventário por credor. Consolidado aqui, antes de tudo, porque o fluxo
    # GEP, o DSCR e o parecer precisam usar a MESMA base de serviço da dívida —
    # duas bases diferentes foi o que já produziu contradição entre a tela e o
    # PDF antes.
    endividamento = consolidar_endividamento(
        dividas                = data.get('dividas'),
        dividas_mensais_legado = data.get('dividas_mensais', 0),
        geracao_caixa_anual    = geracao_caixa_anual,
        parcela_nova           = _parcela_nova,
    )
    _servico_gep = (12 * (_parcela_nova + endividamento['parcela_existente_mensal'])
                    if _parcela_nova > 0 else 0.0)
    fluxo_gep = calcular_fluxo_gep(
        receita_caixa            = _ano1['receita'],
        custo_caixa              = _ano1['custo'],
        valor_rebanho_ini        = _val_ini_cmp['valor_total'],
        valor_rebanho_fim        = _val_fim['valor_total'],
        servico_divida_anual     = _servico_gep,
        reposicao_reprodutores   = _reposicao_reprodutores,
    )

    # COE (R$/@ vendida) = custo_operacional / arrobas_vendidas
    # Arrobas reais por categoria com pesos corretos por ciclo.
    _ciclo_tipo = result.get('tipo', 'CICLO_COMPLETO')
    if _ciclo_tipo in ('CRIA', 'CRIA_RECRIA'):
        # A cria comercializa quatro categorias com pesos bem diferentes:
        # bezerros/bezerras desmamados (~6@), fêmeas excedentes do estoque de
        # novilhas (7,67@) e vacas de descarte (15,33@). Tratar tudo como
        # bezerro subestimava as arrobas vendidas e inflava o COE.
        _arr_bois   = 0.0
        _arr_vacas  = float(_ano1.get('matrizes_descartadas', 0)) * 15.33
        _arr_bezv   = (float(_ano1.get('bezerras_vendidas', 0)) * 6.00
                       + float(_ano1.get('femeas_excedentes', 0)) * 7.67)
        _arr_machos = float(_ano1.get('machos_vendidos', 0)) * 6.67  # bezerros machos
    elif _ciclo_tipo == 'RECRIA':
        # Peso de saída variável; fallback receita/preco captura arrobas corretas
        _arr_bois = _arr_vacas = _arr_bezv = _arr_machos = 0.0
    else:  # CICLO_COMPLETO, ENGORDA, RECRIA_ENGORDA
        _arr_bois   = float(_ano1.get('bois_vendidos', 0)) * 20.53
        _arr_vacas  = float(_ano1.get('descarte_matrizes',
                            _ano1.get('matrizes_descartadas', 0))) * 15.33
        _arr_bezv   = float(_ano1.get('bezerras_vendidas', 0)) * 6.00
        _arr_machos = float(_ano1.get('machos_024_vendidos',
                            _ano1.get('machos_vendidos', 0))) * 10.67
    _arrobas_reais = _arr_bois + _arr_vacas + _arr_bezv + _arr_machos
    if _arrobas_reais <= 0 and result.get('tipo') in ('RECRIA', 'ENGORDA') and _preco_boi_ref > 0 and _ano1.get('receita', 0) > 0:
        # Simulação usa preco × m['preco'] internamente; divide pelo preco efetivo para obter arrobas reais
        _preco_efetivo_sim = _preco_boi_ref * CENARIOS['conservador']['mods']['preco']
        _arrobas_reais = _ano1['receita'] / max(_preco_efetivo_sim, 1)

    if _arrobas_reais > 0:
        _coe_calc = fluxo_gep['custo_operacional'] / _arrobas_reais
        fluxo_gep['coe_por_arroba']    = round(_coe_calc, 2)
        fluxo_gep['coe_benchmark']     = _avaliar_coe(result.get('tipo', 'CICLO_COMPLETO'), _coe_calc)
        fluxo_gep['arrobas_vendidas']  = round(_arrobas_reais, 1)
    else:
        fluxo_gep['coe_por_arroba']   = None
        fluxo_gep['coe_benchmark']    = None
        fluxo_gep['arrobas_vendidas'] = None

    # ── KPIs de custo por cabeça ──────────────────────────────────────────────
    _total_reb   = sum(_va)
    _n_vend_gep  = float(_ano1.get('vendidos', 0) or 1)
    _mat_ini_gep = _va[6] + _va[8]
    fluxo_gep['custo_por_cabeca']       = round(fluxo_gep['custo_operacional'] / max(_total_reb, 1), 2)
    fluxo_gep['receita_por_cab_vendida'] = round(fluxo_gep['receita_vendas'] / _n_vend_gep, 2)
    fluxo_gep['margem_por_cabeca']       = round(fluxo_gep['resultado_operacional'] / max(_total_reb, 1), 2)
    fluxo_gep['total_rebanho']           = int(_total_reb)
    fluxo_gep['n_vendidos_ano1']         = int(_n_vend_gep)
    # Suposição sobre a compra de desmama: sai do implícito para o declarado.
    # É ela que decide se o rebanho encolhe (e a variação de estoque fica
    # negativa) ou se mantém a estrutura pagando a compra todo ano.
    if _ano1.get('compra_desmama_estimada', 0) > 0:
        fluxo_gep['compra_desmama_estimada'] = _ano1['compra_desmama_estimada']
        fluxo_gep['custo_compra_desmama']    = _ano1.get('custo_compra_desmama', 0.0)
        fluxo_gep['repoe_compra_desmama']    = _ano1.get('repoe_compra_desmama', False)
    if result.get('tipo') in ('CRIA', 'CICLO_COMPLETO') and _mat_ini_gep > 0:
        fluxo_gep['receita_por_matriz'] = round(fluxo_gep['receita_vendas'] / _mat_ini_gep, 2)
        fluxo_gep['n_matrizes']         = int(_mat_ini_gep)

    credito_inputs = {k: data.get(k) for k in
                      ('credito_valor', 'prazo_meses', 'juros_aa',
                       'carencia_meses')}
    # A dívida que entra no DSCR é a consolidada, não o número solto do
    # formulário: se o proponente discriminou credores, é a soma das parcelas.
    credito_inputs['dividas_mensais'] = endividamento['parcela_existente_mensal']

    # ── Garantia: valor de execução, não valor de mercado ────────────────────
    # O LTV era calculado no frontend contra o valor de mercado cheio, o que
    # superestima a cobertura: rebanho em penhor não se realiza pela cotação do
    # dia. Passa a ser calculado aqui, com deságio por categoria, e a entrar no
    # parecer e no PDF como qualquer outro número auditável.
    garantia = avaliar_garantia(_val_ini, data.get('credito_valor'))

    # ── Sensibilidade de preço: −15% / base / +15% ───────────────────────────
    # Compensa o modificador de preço do cenário conservador (0.95) para que as
    # variações na tela representem exatamente ±15% do preço de referência.
    _preco_mod_conservador = CENARIOS['conservador']['mods']['preco']
    _servico_base = _servico_gep  # já calculado acima (mesma base do DSCR)
    sensibilidade = []
    for _label, _fator in (('queda_15pct', 0.85), ('base', 1.00), ('alta_15pct', 1.15)):
        _pb_s = _preco_boi_ref * _fator / _preco_mod_conservador
        _cx_s = simular_cenario(
            v, 'conservador', ciclo=result['tipo'],
            preco_arroba=_pb_s,
            custo_arroba=custo_arroba,
            custo_arroba_cria=_custo_fase('custo_arroba_cria'),
            custo_arroba_recria=_custo_fase('custo_arroba_recria'),
            custo_arroba_engorda=_custo_fase('custo_arroba_engorda'),
            preco_boi_arr=_pb_s,
            preco_vaca_arr=(preco_vaca * _fator) if preco_vaca else None,
            preco_bezerra_cab=(preco_bezerra * _fator / _preco_mod_conservador) if preco_bezerra else None,
            preco_bezerro_cab=(preco_bezerro * _fator / _preco_mod_conservador) if preco_bezerro else None,
        )
        _gc_s = _cx_s['anos'][0]['resultado'] - _reposicao_reprodutores
        _dscr_s = round(_gc_s / _servico_base, 2) if _servico_base > 0 else None
        sensibilidade.append({
            'cenario': _label,
            'variacao_pct': round((_fator - 1) * 100),
            'preco_boi': round(_preco_boi_ref * _fator, 2),
            'geracao_caixa': round(_gc_s, 2),
            'dscr': _dscr_s,
            'recomendacao': (
                'aprovar'  if _dscr_s and _dscr_s >= 1.30 else
                'ressalva' if _dscr_s and _dscr_s >= 1.00 else
                'negar'    if _dscr_s is not None else None
            ),
        })

    # ── Sensibilidade de custo: −20% / base / +20% ──────────────────────────
    # Simula o impacto de variação no custo operacional (seca, insumos, mão de obra).
    sensibilidade_custo = []
    def _custo_s(chave, fator):
        base = _custo_fase(chave)
        return round(base * fator, 4) if base is not None else None
    for _fator_c in (0.80, 1.00, 1.20):
        _ca_s = custo_arroba * _fator_c
        _cx_c = simular_cenario(
            v, 'conservador', ciclo=result['tipo'],
            preco_arroba=preco_boi or float(data.get('preco', 320)),
            custo_arroba=_ca_s,
            custo_arroba_cria=_custo_s('custo_arroba_cria', _fator_c),
            custo_arroba_recria=_custo_s('custo_arroba_recria', _fator_c),
            custo_arroba_engorda=_custo_s('custo_arroba_engorda', _fator_c),
            preco_boi_arr=preco_boi, preco_vaca_arr=preco_vaca,
            preco_bezerra_cab=preco_bezerra, preco_bezerro_cab=preco_bezerro,
        )
        _gc_c = _cx_c['anos'][0]['resultado'] - _reposicao_reprodutores
        _dscr_c = round(_gc_c / _servico_base, 2) if _servico_base > 0 else None
        sensibilidade_custo.append({
            'variacao_pct': round((_fator_c - 1) * 100),
            'custo_arroba': round(_ca_s, 2),
            'geracao_caixa': round(_gc_c, 2),
            'dscr': _dscr_c,
            'recomendacao': (
                'aprovar'  if _dscr_c and _dscr_c >= 1.30 else
                'ressalva' if _dscr_c and _dscr_c >= 1.00 else
                'negar'    if _dscr_c is not None else None
            ),
        })

    # SHAP — explicabilidade regulatória (CMN 4.966/2021 / Marco Legal IA)
    shap_explicacao = {}
    try:
        shap_explicacao = explicar_shap(
            v, result['tipo'],
            origem_decisao=result.get('origem_decisao', 'ml'),
            regra_aplicada=result.get('regra_aplicada'),
        )
    except Exception as _e_shap:
        logger.warning(f'SHAP falhou (não crítico): {_e_shap}')

    # ── Projeção multianual (conservador, 5 anos) ────────────────────────────
    # Cada ano: receita, custo, resultado, margem%, DSCR (se houver crédito),
    # rebanho, e sinalização de viabilidade para o analista.
    _projecao_anos = []
    for _ano in _cx['anos']:
        _gc_ano = _ano['resultado'] - _reposicao_reprodutores
        _margem = round(_gc_ano / max(_ano['custo'], 1) * 100, 1)
        _dscr_ano = round(_gc_ano / _servico_base, 2) if _servico_base > 0 else None
        _projecao_anos.append({
            'ano':         _ano['ano'],
            'receita':     round(_ano['receita'], 2),
            'custo':       round(_ano['custo'], 2),
            'resultado':   round(_gc_ano, 2),
            'margem_pct':  _margem,
            'rebanho':     _ano.get('total', 0),
            'matrizes':    _ano.get('matrizes', 0),
            'vendidos':    _ano.get('vendidos', 0),
            'dscr':        _dscr_ano,
            'viavel':      (_dscr_ano is None or _dscr_ano >= 1.0) and _gc_ano > 0,
        })

    parecer = montar_parecer(
        identificacao={'fazenda': fazenda, 'municipio': municipio,
                       'proprietario': data.get('proprietario', '')},
        composicao={'total': int(sum(v)), 'valores': v},
        indicadores=ind, benchmarks=benchmarks,
        consistencia=consistencia, financeiro=breakeven,
        geracao_caixa_anual=geracao_caixa_anual,
        credito=credito_inputs,
        fluxo_gep=fluxo_gep,
        sensibilidade=sensibilidade,
        shap_explicacao=shap_explicacao,
        projecao_anos=_projecao_anos,
        garantia=garantia,
        endividamento=endividamento,
        precos_regional=precos_regional)

    # Persiste no histórico da fazenda apenas quando há fazenda e solicitação.
    fazenda_id = data.get('fazenda_id')
    if fazenda_id and data.get('credito_valor'):
        empresa_id = _resolver_empresa_ativa()
        if empresa_id and db.buscar_fazenda(int(fazenda_id), empresa_id):
            db.salvar_parecer(current_user.id, int(fazenda_id),
                              solicitacao=credito_inputs, parecer=parecer)

    # ── Narrativa IA (Groq Llama 3.3 70B) ───────────────────────────────────────
    # Por padrão NÃO é gerada aqui: a chamada ao Groq leva até 20s e atrasaria
    # todo o parecer. O frontend busca a narrativa em /api/narrativa depois que
    # o resultado já está na tela.
    # Reversível: NARRATIVA_INLINE=1 no ambiente volta ao modo bloqueante.
    _ctx_narrativa = {
        'tipo': result.get('tipo', 'CICLO_COMPLETO'),
        'confianca': result.get('confianca', 0),
        'total_rebanho': int(sum(v)),
        'receita_anual': float(_ano1.get('receita', 0)),
        'geracao_caixa_anual': geracao_caixa_anual,
        'recomendacao': parecer['conclusao'].get('recomendacao', 'ressalva'),
        'dscr': parecer['conclusao'].get('dscr'),
        'limite_credito': parecer['conclusao'].get('capacidade_maxima'),
        'coe_por_arroba': fluxo_gep.get('coe_por_arroba'),
        'consistencia_score': int(consistencia.get('score_consistencia', 100)),
        'fazenda': fazenda,
        'municipio': municipio,
        'proprietario': data.get('proprietario', ''),
    }
    _narrativa_ia = _gerar_narrativa_groq(**_ctx_narrativa) if _NARRATIVA_INLINE else None

    return jsonify({
        **result,
        'indicadores': ind,
        'indicadores_benchmark': ind_bench,
        'benchmarks': benchmarks,
        'benchmarks_nacionais': painel_nacional,
        'avaliacao_embrapa': avaliacao_embrapa,
        'ciclo_info': ciclo_info,
        'breakeven_simples': breakeven,
        'consistencia': consistencia,
        'parecer': parecer,
        'fluxo_gep': fluxo_gep,
        'sensibilidade': sensibilidade,
        'sensibilidade_custo': sensibilidade_custo,
        'custo_desembolso': custo_desembolso,
        'valores': v,
        'registro_id': registro_id,
        'shap_explicacao': shap_explicacao,
        'projecao_anos': _projecao_anos,
        'narrativa_ia': _narrativa_ia,
        # Contexto para o frontend pedir a narrativa de forma assíncrona,
        # sem atrasar a entrega do parecer.
        # Desfrute que a projeção de fato realiza, com a origem explícita:
        # 'projetado' quando vem da simulação, 'informado' quando o analista
        # digitou o valor (que prevalece).
        'desfrute_projetado': {
            # `valor` é o número que foi de fato avaliado pelo benchmark, para
            # que o selo de estado e o número exibido nunca se contradigam.
            # `projetado` é o que a simulação realiza — quando o analista informa
            # um desfrute diferente, os dois aparecem lado a lado.
            'valor':     ind_bench.get('desfrute', desfrute_projetado),
            'projetado': desfrute_projetado,
            'origem':    'informado' if _opt_float(data.get('desfrute_pct')) is not None else 'projetado',
            'vendidos':  int(_vend_ano1),
            'rebanho':   int(sum(v)),
        },
        'narrativa_pendente': (not _NARRATIVA_INLINE) and _narrativa_ativa(),
        'narrativa_contexto': _ctx_narrativa if not _NARRATIVA_INLINE else None,
    })


@app.route('/api/confirmar-ciclo', methods=['POST'])
@login_required
def api_confirmar_ciclo():
    """
    Registra a classificação que o analista confirma ou corrige.

    É o único caminho pelo qual o projeto ganha dado rotulado por humano. Todo
    o conjunto de treino é sintético, gerado a partir de faixas de referência,
    e a acurácia medida sobre ele diz apenas que o modelo aprendeu as faixas
    que escrevemos. Cada confirmação aqui é um caso real, e é o que permitirá
    um dia afirmar que o modelo acerta na realidade.

    O retreino consome apenas `class_conf` (db.exportar_treino), então a
    previsão do modelo nunca realimenta a si mesma.
    """
    data = request.json or {}
    registro_id = data.get('registro_id')
    ciclo = (data.get('ciclo') or '').strip().upper()

    if not registro_id:
        return jsonify({'erro': 'Registro não informado.'}), 400
    if ciclo not in TIPOS:
        return jsonify({'erro': f'Ciclo inválido. Esperado um de: {", ".join(TIPOS)}'}), 400

    registro = db.buscar_registro_por_id(int(registro_id))
    if not registro:
        return jsonify({'erro': 'Registro não encontrado.'}), 404

    db.confirmar(int(registro_id), ciclo)
    concordou = registro.get('class_ml') == ciclo
    logger.info(
        f'[confirmacao] registro {registro_id}: ML={registro.get("class_ml")} '
        f'analista={ciclo} {"concorda" if concordou else "CORRIGE"}'
    )
    return jsonify({
        'ok': True,
        'ciclo': ciclo,
        'class_ml': registro.get('class_ml'),
        'concordou': concordou,
        'total_confirmados': db.contar_confirmados(),
    })


@app.route('/api/narrativa', methods=['POST'])
@login_required
def api_narrativa():
    """
    Narrativa do parecer gerada pela IA, fora do caminho crítico.

    Separado de /api/classificar de propósito: a chamada ao Groq leva até 20s
    e o parecer não pode esperar por ela. O frontend renderiza o resultado
    primeiro e busca a narrativa aqui em seguida.
    """
    if not _narrativa_ativa():
        return jsonify({'erro': 'IA não configurada — defina GROQ_API_KEY.'}), 503

    ctx = (request.json or {}).get('contexto') or {}
    if not ctx.get('tipo'):
        return jsonify({'erro': 'Contexto do parecer ausente.'}), 400

    permitido = {
        'tipo', 'confianca', 'total_rebanho', 'receita_anual',
        'geracao_caixa_anual', 'recomendacao', 'dscr', 'limite_credito',
        'coe_por_arroba', 'consistencia_score', 'fazenda', 'municipio',
        'proprietario',
    }
    texto = _gerar_narrativa_groq(**{k: v for k, v in ctx.items() if k in permitido})
    if texto is None:
        return jsonify({'erro': 'Serviço de IA temporariamente indisponível.'}), 503
    return jsonify({'narrativa': texto})

@app.route('/api/chat', methods=['POST'])
@login_required
def api_chat():
    """Chat com o parecer de crédito via Groq."""
    from services.groq_narrativa import gerar_resposta_chat, _feature_ativa
    if not _feature_ativa():
        return jsonify({'erro': 'IA não configurada — adicione GROQ_API_KEY nas variáveis de ambiente.'}), 503

    data = request.json or {}
    mensagem = (data.get('mensagem') or '').strip()
    if not mensagem:
        return jsonify({'erro': 'Mensagem vazia'}), 400
    if len(mensagem) > 800:
        return jsonify({'erro': 'Mensagem muito longa (máx. 800 caracteres)'}), 400

    historico = data.get('historico') or []
    contexto  = data.get('contexto') or {}

    resposta = gerar_resposta_chat(mensagem, historico, contexto)
    if resposta is None:
        return jsonify({'erro': 'Serviço de IA temporariamente indisponível. Tente novamente.'}), 503

    return jsonify({'resposta': resposta})


# ═══════════════════════════════════════════════════════════════════════════
# WHATSAPP — o mesmo chat do parecer, no canal onde o analista já está
# ═══════════════════════════════════════════════════════════════════════════
# O analista de campo não abre o sistema no meio de uma visita; abre o
# WhatsApp. Sem WHATSAPP_TOKEN/WHATSAPP_PHONE_ID no ambiente estas rotas
# devolvem 404 — o webhook não existe para quem não configurou.
from services import whatsapp as _wa
from services.groq_narrativa import gerar_resposta_chat as _gerar_resposta_chat_wa


def _contexto_parecer_para_chat(p: dict) -> dict:
    """Achata um parecer salvo no formato que gerar_resposta_chat espera."""
    parecer = (p or {}).get('parecer') or {}
    concl   = parecer.get('conclusao') or {}
    solic   = (p or {}).get('solicitacao') or {}
    ident   = parecer.get('identificacao') or {}
    return {
        'tipo':          solic.get('tipo') or parecer.get('tipo'),
        'fazenda':       ident.get('fazenda'),
        'municipio':     ident.get('municipio'),
        'recomendacao':  concl.get('recomendacao'),
        'dscr':          concl.get('dscr_minimo', concl.get('dscr')),
        'parcela_mensal': concl.get('parcela_mensal'),
        'geracao_caixa_anual': concl.get('geracao_caixa_anual'),
        'capacidade_maxima':   concl.get('capacidade_maxima'),
        'garantia':      parecer.get('garantia'),
        'endividamento': parecer.get('endividamento'),
        'justificativa': concl.get('justificativa'),
    }


def _responder_whatsapp(telefone: str, texto: str) -> str:
    """
    Monta a resposta a uma mensagem. Puro o suficiente para ser testado sem HTTP.

    Um telefone não vinculado nunca recebe dado de crédito: a resposta é a
    instrução de vinculação. Vincular exige um código gerado por um analista
    logado no sistema.
    """
    variantes = _wa.variantes_telefone(telefone)
    uid = db.buscar_user_por_telefone(variantes)

    # Vinculação: mensagem que é só um código de 6 dígitos.
    # Vale também para número já vinculado — o analista pode trocar de conta, e
    # exigir desvincular antes seria um beco sem saída pelo WhatsApp.
    limpo = texto.strip()
    if limpo.isdigit() and len(limpo) == 6:
        novo = db.consumir_codigo_whatsapp(limpo, _wa.normalizar_telefone(telefone))
        if novo:
            u = db.buscar_usuario_id(novo)
            nome = (u or {}).get('nome', '')
            return (f'Número vinculado a {nome}. '
                    f'Pergunte o que quiser sobre o seu último parecer de crédito.')
        if not uid:
            return 'Código inválido ou expirado. Gere um novo no sistema.'
        # Já vinculado e não era código válido: pode ser pergunta. Segue.

    if not uid:
        return ('Número não vinculado. Entre no BovCredit, gere um código de '
                'vinculação e envie os 6 dígitos aqui.')

    p = db.ultimo_parecer_do_usuario(uid)
    if not p:
        return ('Você ainda não tem parecer emitido. Gere um no sistema e volte '
                'a perguntar aqui.')

    resposta = _gerar_resposta_chat_wa(texto, [], _contexto_parecer_para_chat(p))
    if not resposta:
        return 'Não consegui responder agora. Tente novamente em instantes.'
    return resposta


@app.route('/webhook/whatsapp', methods=['GET'])
def whatsapp_verificacao():
    """Handshake que a Meta faz ao cadastrar a URL do webhook."""
    if not _wa._feature_ativa():
        abort(404)
    challenge = _wa.verificar_webhook(request.args)
    if challenge is None:
        abort(403)
    return challenge, 200, {'Content-Type': 'text/plain'}


@app.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_webhook():
    """
    Recebe mensagens da Meta.

    Responde 200 em qualquer caso depois de validada a assinatura: erro faz a
    Meta reenviar em backoff, e a mesma pergunta seria respondida duas vezes.
    """
    if not _wa._feature_ativa():
        abort(404)
    if not _wa.validar_assinatura(request.get_data(),
                                  request.headers.get('X-Hub-Signature-256')):
        logger.warning('[whatsapp] assinatura inválida — requisição descartada')
        abort(403)

    for msg in _wa.extrair_mensagens(request.get_json(silent=True) or {}):
        try:
            resposta = _responder_whatsapp(msg['telefone'], msg['texto'])
            _wa.enviar_mensagem(msg['telefone'], resposta)
        except Exception:
            logger.exception('[whatsapp] falha ao responder %s', msg.get('telefone'))
    return jsonify({'ok': True})


@app.route('/api/whatsapp/codigo', methods=['POST'])
@login_required
def api_whatsapp_codigo():
    """Gera o código de uso único que vincula o WhatsApp do analista à conta."""
    if not _wa._feature_ativa():
        return jsonify({'erro': 'Canal WhatsApp não configurado.'}), 503
    codigo = db.criar_codigo_whatsapp(int(current_user.id))
    return jsonify({'codigo': codigo, 'validade_min': 15})


# ── Cache em memória para cotações (TTL 30 min) ──────────────────────────────
import time as _time
_cotacoes_cache: dict = {}
_cotacoes_cache_ts: float = 0.0
_COTACOES_TTL = 30 * 60  # 30 minutos


def _cotacoes_cached() -> dict:
    global _cotacoes_cache, _cotacoes_cache_ts
    agora = _time.monotonic()
    if _cotacoes_cache and (agora - _cotacoes_cache_ts) < _COTACOES_TTL:
        return _cotacoes_cache
    fresh = db.obter_cotacoes_atuais() or {}
    _cotacoes_cache = fresh
    _cotacoes_cache_ts = agora
    return fresh


def _invalidar_cache_cotacoes():
    global _cotacoes_cache_ts
    _cotacoes_cache_ts = 0.0


@app.route('/api/precos/live', methods=['GET'])
@login_required
def api_precos_live():
    """Cotação mais recente por categoria (boi/vaca R$/@, bezerro/bezerra R$/cab)."""
    from services.precos_diarios import BEZERRO_REF, bezerra_de
    try:
        c = _cotacoes_cached()
        tem = c.get('boi', 0) > 0 or c.get('vaca', 0) > 0
        bezerro = c.get('bezerro') or BEZERRO_REF
        return jsonify({
            'ok': True,
            'origem': 'banco' if tem else 'referência',
            'precos': {
                'boi': c.get('boi', 0),
                'vaca': c.get('vaca', 0),
                'boi_china': c.get('boi_china', 0),
                'bezerro': bezerro,
                'bezerra': c.get('bezerra') or bezerra_de(bezerro),
            }
        })
    except Exception as e:
        logger.error(f"Erro ao buscar cotações: {e}", exc_info=True)
        return jsonify({'erro': str(e)}), 500

# ── Notícias agropecuárias — RSS ticker ──────────────────────────────────────
import xml.etree.ElementTree as _ET
_noticias_cache: list = []
_noticias_cache_ts: float = 0.0
_NOTICIAS_TTL = 20 * 60   # 20 minutos

_RSS_FEEDS = [
    # Canal Rural
    'https://www.canalrural.com.br/feed/',
    # G1 Agronegócios
    'https://g1.globo.com/rss/g1/economia/agronegocios/',
]
_PALAVRAS_AGRO = {
    'boi', 'vaca', 'rebanho', 'pecuária', 'pecuaria', 'arroba', 'cepea',
    'nelore', 'bezerro', 'gado', 'agro', 'rural', 'soja', 'milho',
    'safra', 'fazenda', 'produtor', 'carne', 'frigorífico', 'frigorifico',
}


def _buscar_rss(url: str, sess) -> list[dict]:
    try:
        r = sess.get(url, timeout=10, headers=_SCRAPER_HEADERS)
        r.raise_for_status()
        root = _ET.fromstring(r.content)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        itens = []
        # RSS 2.0
        for item in root.iter('item'):
            titulo = (item.findtext('title') or '').strip()
            link   = (item.findtext('link') or '').strip()
            data   = (item.findtext('pubDate') or '').strip()
            if titulo and link:
                itens.append({'titulo': titulo, 'link': link, 'data': data})
        # Atom
        if not itens:
            for entry in root.findall('atom:entry', ns):
                titulo = (entry.findtext('atom:title', namespaces=ns) or '').strip()
                link_el = entry.find('atom:link', ns)
                link = (link_el.get('href', '') if link_el is not None else '').strip()
                data = (entry.findtext('atom:published', namespaces=ns) or '').strip()
                if titulo and link:
                    itens.append({'titulo': titulo, 'link': link, 'data': data})
        logger.info(f'[RSS] {url} → {len(itens)} itens | status={r.status_code} | tag-raiz={root.tag}')
        return itens
    except Exception as e:
        logger.warning(f'[RSS] Falha em {url}: {e}')
        return []


def _filtrar_agro(itens: list[dict]) -> list[dict]:
    resultado = []
    for it in itens:
        t = it['titulo'].lower()
        if any(p in t for p in _PALAVRAS_AGRO):
            resultado.append(it)
    return resultado or itens  # sem filtro se nenhum passou


def _noticias_fresh() -> list:
    global _noticias_cache, _noticias_cache_ts
    agora = _time.monotonic()
    if _noticias_cache and (agora - _noticias_cache_ts) < _NOTICIAS_TTL:
        return _noticias_cache
    sess = _session_com_retry()
    todos = []
    for url in _RSS_FEEDS:
        todos.extend(_buscar_rss(url, sess))
    filtrados = _filtrar_agro(todos)[:30]
    if filtrados:
        _noticias_cache = filtrados
        _noticias_cache_ts = agora
    return _noticias_cache or []


@app.route('/api/noticias', methods=['GET'])
@login_required
def api_noticias():
    """Retorna até 30 notícias agropecuárias de RSS público (Canal Rural + G1 Agro).

    Cache de 20 minutos — não bate nos feeds a cada chamada do ticker.
    """
    try:
        itens = _noticias_fresh()
        return jsonify({'ok': True, 'noticias': itens, 'total': len(itens)})
    except Exception as e:
        logger.error(f'[RSS] Erro no endpoint: {e}', exc_info=True)
        return jsonify({'ok': False, 'noticias': [], 'erro': str(e)}), 500


@app.route('/api/cenario', methods=['POST'])
@login_required
def api_cenario():
    data = request.json
    v = data.get('valores', [])
    cenario = data.get('cenario', 'crescimento')
    # Valida se o cenário existe
    if cenario not in CENARIOS:
        return jsonify({'erro': f'Cenário "{cenario}" não encontrado'}), 400

    params = {
        'nat_pct':       float(data.get('nat', 75)),
        'mort_pct':      float(data.get('mort', 3)),
        'desc_pct':      float(data.get('desc', 30)),
        'preco_arroba':  float(data.get('preco', 320)),
        'custo_arroba':  float(data.get('custo', 57)),
        'peso_arroba':   float(data.get('peso', 16)),
        'prop_boi':      float(data.get('propboi', 30)),
        'renov_boi_pct': float(data.get('renovboi', 20)),
        'venda_bez_pct': float(data.get('vendbez', 30)),
    }
    for fase in ('custo_arroba_cria', 'custo_arroba_recria', 'custo_arroba_engorda'):
        v_ = float(data.get(fase) or 0)
        if v_ > 0:
            params[fase] = v_
    if len(v) != 10:
        return jsonify({'erro': 'Valores inválidos'}), 400
    result = simular_cenario(v, cenario, **params)
    return jsonify(result)

@app.route('/api/cenarios', methods=['GET'])
def api_cenarios():
    return jsonify({k: {'nome': v['nome'], 'desc': v['desc'], 'emoji': v['emoji']}
                    for k, v in CENARIOS.items()})

# ── Rota: Matemática Financeira da Arroba ──────────────────────────────────
@app.route('/api/estimativa-valor', methods=['POST'])
@login_required
def api_estimativa_valor():
    """Calcula o valor estimado de um animal baseado no peso, sexo e cotação do dia."""
    data = request.json
    peso_vivo = float(data.get('peso_vivo', 0))
    sexo = data.get('sexo', 'M').upper()

    if peso_vivo <= 0:
        return jsonify({"erro": "Peso vivo inválido."}), 400

    cotacoes = db.obter_cotacoes_atuais()
    preco_arroba = cotacoes.get('boi', 0.0) if sexo == 'M' else cotacoes.get('vaca', 0.0)

    if preco_arroba == 0.0:
        return jsonify({"erro": "Cotação indisponível no banco de dados."}), 503

    _rendimento_carcaca = 0.55 if sexo == 'M' else 0.52
    peso_carcaca_arrobas = peso_vivo * _rendimento_carcaca / 15.0
    valor_estimado = peso_carcaca_arrobas * preco_arroba

    return jsonify({
        "sexo": sexo,
        "peso_vivo_kg": peso_vivo,
        "peso_estimado_arrobas": round(peso_carcaca_arrobas, 2),
        "cotacao_aplicada": preco_arroba,
        "valor_estimado_reais": round(valor_estimado, 2)
    })

# ── Leitura de PDF ──────────────────────────────────────────────────────────
def extrair_texto_pdf(path: str) -> str:
    """Extrai texto de PDF: pdftotext → pdfplumber → OCR (Tesseract) para PDFs escaneados."""
    # 1. pdftotext (mais fiel ao layout)
    try:
        result = subprocess.run(
            ['pdftotext', '-layout', path, '-'],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # 2. pdfplumber (funciona sem poppler)
    text = ''
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text += (page.extract_text() or '') + '\n'
        if text.strip():
            return text
    except Exception as e:
        raise RuntimeError(f'Não foi possível extrair texto do PDF: {e}')

    # 3. OCR com Tesseract (PDF escaneado / baseado em imagem)
    try:
        import pytesseract
        import pdfplumber
        # Localiza o Tesseract (Windows ou PATH do sistema)
        tess_win = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        if os.path.exists(tess_win):
            pytesseract.pytesseract.tesseract_cmd = tess_win

        ocr_text = ''
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                img = page.to_image(resolution=200).original
                # 'por+eng' se disponível, senão 'eng'
                try:
                    ocr_text += pytesseract.image_to_string(img, lang='por+eng') + '\n'
                except pytesseract.TesseractError:
                    ocr_text += pytesseract.image_to_string(img, lang='eng') + '\n'
        if ocr_text.strip():
            logger.info("PDF escaneado: texto extraído via OCR (%d chars)", len(ocr_text))
            return ocr_text
    except Exception as e:
        logger.warning("OCR falhou: %s", e)

    return text  # vazio — deixa o parser lidar

def detectar_origem(text: str) -> str:
    """Detecta agência/estado do documento — delega para pdf_parsers."""
    from pdf_parsers import detectar_origem as _det
    return _det(text)

@app.route('/api/ler-pdf', methods=['POST'])
@login_required
def api_ler_pdf():
    if 'pdf' not in request.files:
        return jsonify({'erro': 'Nenhum arquivo enviado'}), 400
    f = request.files['pdf']
    if not f.filename.lower().endswith('.pdf'):
        return jsonify({'erro': 'Apenas arquivos PDF são aceitos'}), 400

    # delete=False: necessário no Windows (NamedTemporaryFile bloqueia o arquivo
    # enquanto aberto, impedindo que werkzeug abra pelo nome novamente)
    tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    tmp_path = tmp.name
    tmp.close()
    try:
        f.save(tmp_path)
        text = extrair_texto_pdf(tmp_path)
        estado = request.form.get('estado', '').upper().strip()
        _ESTADO_ORIGEM = {
            'MT': 'INDEA', 'RO': 'IDARON', 'MS': 'IAGRO_MS',
            'GO': 'AGRODEFESA_GO', 'MA': 'AGED_MA',
            'TO': 'ADAPEC_TO', 'PA': 'ADEPARA_PA',
        }
        orig = _ESTADO_ORIGEM.get(estado) or detectar_origem(text)
        if orig == 'DECLARACAO_IDARON':
            dados = parsear_declaracao_idaron(text)
        elif orig == 'IDARON':
            dados = parsear_idaron(text, pdf_path=tmp_path)
        elif orig in ORIGENS_INDEA:       # MT (5 faixas)
            dados = parsear_indea(text, pdf_path=tmp_path)
        elif orig == 'IAGRO_MS':          # MS — modLeitorMS.bas
            dados = parsear_iagro_ms(text)
        elif orig == 'AGED_MA':           # MA — modLeitorMA.bas
            dados = parsear_aged_ma(text)
        elif orig == 'GO_DEC_WEB':         # GO declaração web
            dados = parsear_go_declaracao_web(text)
        elif orig == 'AGRODEFESA_GO':     # GO ficha — modLeitorGOFicha.bas
            dados = parsear_agrodefesa_go(text)
        elif orig == 'ADAPEC_TO':         # TO — modLeitorTO.bas
            dados = parsear_adapec_to(text, pdf_path=tmp_path)
        elif orig == 'ADEPARA_PA':        # PA — modLeitorPA.bas
            dados = parsear_adepara_pa(text)
        else:
            dados = parsear_generico(text)
            if dados['total'] == 0:
                dados = parsear_idaron(text, pdf_path=tmp_path)
            if dados['total'] == 0:
                dados = parsear_indea(text, pdf_path=tmp_path)
        dados['origem'] = orig
        return jsonify(dados)
    except Exception as e:
        logger.error(f"Erro ao processar PDF: {e}", exc_info=True)
        return jsonify({'erro': str(e)}), 500
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

@app.route('/api/template/download', methods=['GET'])
@login_required
def api_template_download():
    """Baixa o template oficial de composição de rebanho para o produtor preencher."""
    return send_from_directory(
        os.path.join(app.static_folder, 'templates'),
        'modelo_composicao_rebanho.xlsx',
        as_attachment=True,
    )


@app.route('/api/ficha/download', methods=['GET'])
@login_required
def api_ficha_download():
    """Baixa o template XLSM de CONSOLIDADO preenchido com exemplo."""
    return send_file(
        os.path.join(app.static_folder, 'ficha_consolidado_exemplo.xlsm'),
        mimetype='application/vnd.ms-excel.sheet.macroEnabled.12',
        as_attachment=True,
        download_name='ficha_consolidado_exemplo.xlsm',
    )


@app.route('/api/importar-ficha-excel', methods=['POST'])
@login_required
def api_importar_ficha_excel():
    """Importa a planilha 'Classificação de Rebanho - Fichas' (CONSOLIDADO).

    Aceita .xlsx ou .xlsm. Devolve lista de fazendas com seus rebanhos já
    mapeados para o formato v[] de 10 posições usado no classificador.

    Resposta JSON:
      { "fazendas": [{"fazenda": str, "valores": [10 ints], "total": int}, ...] }
    """
    if 'arquivo' not in request.files:
        return jsonify({'erro': 'Envie o arquivo no campo "arquivo"'}), 400
    f = request.files['arquivo']
    if not f.filename.lower().endswith(('.xlsx', '.xlsm')):
        return jsonify({'erro': 'Apenas .xlsx ou .xlsm são aceitos'}), 400

    try:
        conteudo = f.read()
        fazendas = parsear_ficha_excel(conteudo)
        if not fazendas:
            return jsonify({'erro': 'Nenhuma fazenda com animais encontrada na aba CONSOLIDADO'}), 400
        uf = (request.form.get('uf') or '').strip().upper()
        if uf:
            for faz in fazendas:
                faz.setdefault('uf', uf)
        return jsonify({'fazendas': fazendas, 'total_fazendas': len(fazendas)})
    except KeyError:
        return jsonify({'erro': 'Aba CONSOLIDADO não encontrada — verifique o formato do arquivo'}), 400
    except Exception as e:
        logger.error(f'Erro ao importar ficha Excel: {e}', exc_info=True)
        return jsonify({'erro': str(e)}), 500


@app.route('/api/ler-planilha', methods=['POST'])
@login_required
def api_ler_planilha():
    """Lê o template preenchido e já retorna a análise de consistência do rebanho."""
    if 'planilha' not in request.files:
        return jsonify({'erro': 'Nenhum arquivo enviado'}), 400
    f = request.files['planilha']
    if not f.filename.lower().endswith(('.xlsx', '.xlsm')):
        return jsonify({'erro': 'Apenas planilhas .xlsx são aceitas'}), 400

    tmp = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
    tmp_path = tmp.name
    tmp.close()
    try:
        f.save(tmp_path)
        dados = ler_template(tmp_path)
        dados['consistencia'] = analisar_consistencia(dados['valores'])
        return jsonify(dados)
    except ValueError as e:
        return jsonify({'erro': str(e)}), 400
    except Exception as e:
        logger.error(f"Erro ao processar planilha: {e}", exc_info=True)
        return jsonify({'erro': str(e)}), 500
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@app.route('/api/reconciliacao', methods=['POST'])
@login_required
def api_reconciliacao():
    """Cruza o rebanho declarado em Ficha Sanitária, IR e GTA.

    Detecta garantia superavaliada (rebanho de papel > rebanho físico).
    """
    data = request.get_json() or {}
    totais = {
        'ficha': data.get('ficha'),
        'ir': data.get('ir'),
        'gta': data.get('gta'),
    }
    try:
        return jsonify(reconciliar(totais))
    except ValueError as e:
        return jsonify({'erro': str(e)}), 400
    except Exception as e:
        logger.error(f"Erro na reconciliação: {e}", exc_info=True)
        return jsonify({'erro': str(e)}), 500


@app.route('/api/parse-text', methods=['POST'])
@login_required
def api_parse_text():
    """Reprocessa um texto extraído de PDF com o parser escolhido."""
    data = request.get_json() or {}
    text = data.get('text', '')
    if not text:
        return jsonify({'erro': 'Campo "text" é obrigatório.'}), 400
    origem = data.get('origem')
    try:
        orig = origem or detectar_origem(text)
        if orig == 'DECLARACAO_IDARON':
            dados = parsear_declaracao_idaron(text)
        elif orig == 'IDARON':
            dados = parsear_idaron(text)
        elif orig in ORIGENS_INDEA:
            dados = parsear_indea(text)
        elif orig == 'IAGRO_MS':
            dados = parsear_iagro_ms(text)
        elif orig == 'AGED_MA':
            dados = parsear_aged_ma(text)
        elif orig == 'AGRODEFESA_GO':
            dados = parsear_agrodefesa_go(text)
        elif orig == 'ADAPEC_TO':
            dados = parsear_adapec_to(text)
        elif orig == 'ADEPARA_PA':
            dados = parsear_adepara_pa(text)
        else:
            dados = parsear_generico(text)
            if dados['total'] == 0:
                dados = parsear_idaron(text)
            if dados['total'] == 0:
                dados = parsear_indea(text)
        dados['origem'] = orig
        return jsonify(dados)
    except Exception as e:
        logger.error(f"Erro no parse-text: {e}", exc_info=True)
        return jsonify({'erro': str(e)}), 500

# ─────────────────────────────────────────────
# INÍCIO DA APLICAÇÃO
# ─────────────────────────────────────────────
if __name__ == '__main__':
    logger.info("🚀 BoviML iniciado em http://localhost:5050")
    app.run(debug=True, port=5050)