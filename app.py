"""
Plataforma de Análise de Crédito Pecuário — Servidor Flask
"""
import logging
import os
import re
import io
import tempfile
import subprocess
import threading
from functools import wraps

from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, send_from_directory, send_file, session, abort
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from apscheduler.schedulers.background import BackgroundScheduler

from ml_engine import (
    treinar_modelo, classificar, calcular_indicadores,
    simular_cenario, carregar_modelo, CENARIOS,
    comparar_cenarios,
    avaliar_benchmarks, extrair_indicadores_benchmark, calcular_breakeven_simples,
    explicar_shap, TIPOS, PARAMS_POR_CICLO,
)
import database as db
from services import assistente as _assistente
from services.documentos import (
    impressao as doc_impressao, comparar as doc_comparar,
)

# Importações do PDF parsers (evitamos sobrescrever com definições locais)
from pdf_parsers import (
    parsear_idaron, parsear_indea, parsear_declaracao_idaron,
    parsear_resumo_fazendas,
    parsear_generico,
    parsear_iagro_ms, parsear_aged_ma, parsear_agrodefesa_go,
    parsear_adapec_to, parsear_adepara_pa,
    parsear_go_declaracao_web,
    ORIGENS_GENERICAS, ORIGENS_INDEA,
)

from services.importar_excel import parsear_ficha_excel, validar_fazendas_importadas
from services.fichas_rebanho import read_ficha_pdf
from services.fichas_rebanho.consolidator import consolidar_registros
from services.fichas_rebanho.validator import validar_registros
from services.fichas_rebanho.log import registros_para_log

from scraper import obter_precos_arroba, _session_com_retry, _HEADERS as _SCRAPER_HEADERS

from parsers.composicao_rebanho import ler_template
from services.consistencia_rebanho import analisar_consistencia, analisar_consistencia_historica
from services.benchmarks_nacionais import (
    avaliar_nacional, avaliar_zootecnico, CICLO_CATEGORIAS,
    calcular_desfrute, alerta_liquidacao,
)
from services.parecer_credito import montar_parecer, cronograma_price
from services.parecer_pdf import gerar_pdf_parecer
from services.pesos_rebanho import arrobas_categorias
from services.parametros_zootecnicos import (
    natalidade_de_prenhez, avaliar_reposicao as _avaliar_reposicao)
from services.nivel_tecnologico import (
    avaliar as _avaliar_nivel, conferir_produtividade as _conferir_produtividade,
    gmd_do_nivel as _gmd_do_nivel)
from services.custos_desembolso import (
    custo_arroba_de_desembolso, COMPONENTES, custo_arroba_padrao,
    perfil_do_nivel as _perfil_do_nivel,
    desembolso_operacional as _desembolso_operacional,
)
from services.economic_engine import calculate_economic_result
from services.reconciliacao import reconciliar
from services.fluxo_caixa_gep import valor_rebanho_gep
from services.garantia import avaliar_garantia
from services.qualidade_dados import analisar_qualidade_dados
from services.explicacao_classificacao import montar_explicacao_classificacao
from services.validacao_zootecnica import analisar_validacoes_zootecnicas
from services.checklist_credito import checklist_credito
from services.fluxo_mensal_credito import projetar_fluxo_mensal
from services.rating_credito import calcular_rating
from services.precos_regionais import aplicar as aplicar_preco_regional
from services.analysis_pipeline import run_full_analysis
from services import auditoria as _aud
from services import totp as _totp
import time as _time
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

# SHAP fora do caminho crítico, pelo mesmo motivo da narrativa — só que aqui o
# custo é MEMÓRIA, não latência.
#
# Cada classificação construía os TreeExplainer dos quatro estimadores do
# ensemble e alocava ~160 MB até o fim da chamada. Medido em processo real:
# 300 MB com o modelo carregado, 459 MB durante uma classificação. Com dois
# workers atendendo classificações ao mesmo tempo dava 620 MB contra um teto
# de 512, o processo morria e o gateway devolvia 502 na tela de classificar.
#
# O paliativo foi descer para um worker. Tirando o SHAP daqui, o pico deixa de
# coincidir com a classificação e dois workers voltam a caber.
#
# A explicabilidade NÃO é perdida: o frontend busca em /api/shap logo após
# renderizar e funde o resultado no parecer, de modo que o PDF continua
# saindo com os fatores — boa prática de governança e revisão humana.
#
# Reversível: SHAP_INLINE=1 volta a calcular dentro de /api/classificar.
_SHAP_INLINE = os.environ.get('SHAP_INLINE', '0') == '1'


def _calcular_shap(valores, tipo, origem_decisao='ml', regra_aplicada=None):
    """SHAP com a mesma guarda de sempre: falhar aqui nunca derruba o parecer."""
    try:
        return explicar_shap(valores, tipo, origem_decisao=origem_decisao,
                             regra_aplicada=regra_aplicada)
    except Exception as e:
        logger.warning(f'SHAP falhou (não crítico): {e}')
        return {}

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
_https_producao = bool(
    os.environ.get('RAILWAY_ENVIRONMENT') or os.environ.get('RENDER')
    or os.environ.get('FLY_APP_NAME') or os.environ.get('DATABASE_URL')
)
app.config['SESSION_COOKIE_SECURE'] = _https_producao
app.config['REMEMBER_COOKIE_HTTPONLY'] = True
app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'
app.config['REMEMBER_COOKIE_SECURE'] = _https_producao

# ── Security headers via after_request ───────────────────────────────────────
@app.after_request
def _set_security_headers(response):
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault(
        'Content-Security-Policy',
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline' "
        "https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
        "script-src 'self' 'unsafe-inline'; connect-src 'self'; "
        "frame-ancestors 'self'; base-uri 'self'; form-action 'self'"
    )
    if _https_producao:
        response.headers.setdefault('Strict-Transport-Security',
                                    'max-age=31536000; includeSubDomains')
    return response

_secret_key = os.environ.get('SECRET_KEY')
if not _secret_key:
    if os.environ.get('FLASK_ENV') == 'production' or os.environ.get('RAILWAY_ENVIRONMENT'):
        raise RuntimeError('SECRET_KEY não definida em produção — defina a variável de ambiente.')
    _secret_key = 'orkavyn-dev-secret-local'
app.secret_key = _secret_key

# ── CSRF protection para rotas admin ─────────────────────────────────────────
def _csrf_token() -> str:
    if 'csrf_token' not in session:
        session['csrf_token'] = _secrets.token_hex(32)
    return session['csrf_token']

app.jinja_env.globals['csrf_token'] = _csrf_token

@app.before_request
def _verificar_csrf():
    """Protege toda mutação autenticada, inclusive endpoints JSON e upload."""
    if (request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}
            and current_user.is_authenticated):
        esperado = session.get('csrf_token')
        # Sessões antigas recebem o token na próxima renderização do app. As
        # rotas admin sempre o criam no formulário e continuam falhando fechado.
        if not esperado and not request.path.startswith('/admin'):
            return None
        token = (request.form.get('csrf_token', '')
                 or request.headers.get('X-CSRF-Token', ''))
        if not token or not _secrets.compare_digest(token, esperado or ''):
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

# ── Scheduler: exatamente UM, no processo inteiro ────────────────────────────
# Com mais de um worker, cada um iniciaria o seu — e o scraper bateria N vezes
# na mesma fonte, no mesmo minuto. Sob gunicorn quem chama é o hook
# `when_ready` do gunicorn.conf.py, que roda uma única vez no master, antes do
# fork dos workers. A thread do scheduler não é herdada pelos filhos (só a
# thread que chama fork sobrevive), então ela vive no master e só lá.
scheduler = None
_scheduler_iniciado = False


def iniciar_scheduler():
    """Idempotente — chamar duas vezes não cria dois agendadores."""
    global scheduler, _scheduler_iniciado
    if _scheduler_iniciado:
        return scheduler
    import threading
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(rotina_diaria_cotacoes, 'cron', hour=8, minute=0)
    scheduler.start()
    threading.Thread(target=rotina_diaria_cotacoes, daemon=True).start()
    _scheduler_iniciado = True
    logger.info('⏰ Scheduler de cotações iniciado (pid %s)', os.getpid())
    return scheduler


# Fora do gunicorn (python app.py), o start é aqui mesmo. O Reloader do Flask
# sobe o processo duas vezes em debug, daí a checagem de WERKZEUG_RUN_MAIN.
if os.environ.get('SCHEDULER_VIA_HOOK') != '1' and (
        os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug):
    iniciar_scheduler()

# ── Auditoria de acesso ──────────────────────────────────────────────────────
# Sem trilha, a instituição não responde à própria auditoria interna sobre quem
# consultou dado de crédito de qual cliente. Ver services/auditoria.py.
def _auditar(evento, *, recurso=None, recurso_id=None, detalhe=None,
             sucesso=True, email=None):
    """Registra um evento. Nunca levanta — a operação vem primeiro."""
    uid = None
    mail = email
    try:
        if current_user and current_user.is_authenticated:
            uid = int(current_user.id)
            mail = mail or current_user.email
    except Exception:
        pass
    db.registrar_acesso(evento, user_id=uid, user_email=mail, recurso=recurso,
                        recurso_id=recurso_id, detalhe=detalhe,
                        ip=_aud.ip_da_requisicao(request), sucesso=sucesso)


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
            # Segundo fator: a sessão só é criada depois do código. Guardar o
            # id numa chave separada — e não em '_user_id' — é o que impede
            # que a senha sozinha já autentique.
            if db.totp_estado(u['id'])['ativo']:
                session['totp_pendente'] = u['id']
                session['totp_desde'] = _time.time()
                return redirect(url_for('login_2fa'))
            login_user(User(u), remember=True)
            _auditar(_aud.LOGIN, email=email)
            return redirect(url_for('app_main'))
        _auditar(_aud.LOGIN_FALHOU, email=email, sucesso=False)
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

@app.route('/api/admin/lgpd/inventario', methods=['GET'])
@admin_required
def api_lgpd_inventario():
    """Registro das operações de tratamento (Art. 37) — o que se guarda e por quê."""
    from services import lgpd
    return jsonify({
        'inventario': lgpd.resumo_inventario(),
        'retencao_auditoria_dias': lgpd.RETENCAO_AUDITORIA_DIAS,
        'aviso': ('Cobre as obrigações que se implementam. Base legal, '
                  'encarregado, política de privacidade e contrato de operador '
                  'são decisão da empresa, não do sistema.'),
    })


@app.route('/api/admin/lgpd/exportar/<int:uid>', methods=['GET'])
@admin_required
def api_lgpd_exportar(uid):
    """Portabilidade (Art. 18, V): tudo que o sistema guarda sobre um usuário."""
    dados = db.exportar_dados_usuario(uid)
    if not dados:
        return jsonify({'erro': 'Usuário não encontrado.'}), 404
    _auditar('lgpd_exportacao', recurso='usuario', recurso_id=uid)
    return jsonify(dados)


@app.route('/api/admin/lgpd/anonimizar/<int:uid>', methods=['POST'])
@admin_required
def api_lgpd_anonimizar(uid):
    """
    Direito de eliminação (Art. 18). Anonimiza em vez de excluir: o registro
    dos eventos permanece na trilha, a pessoa deixa de ser identificável.

    Exige confirmação explícita no corpo — é irreversível e não há de-para.
    """
    if (request.json or {}).get('confirmo') is not True:
        return jsonify({
            'erro': 'Operação irreversível. Envie {"confirmo": true} para prosseguir.',
            'efeito': ('A conta fica inutilizável, e-mail e nome viram pseudônimo '
                       'estável, IP é removido da trilha e o vínculo de WhatsApp '
                       'é apagado. Pareceres emitidos NÃO são apagados — são dado '
                       'do cliente da consultoria.'),
        }), 400
    r = db.anonimizar_usuario(uid)
    if not r.get('ok'):
        return jsonify(r), 404
    _auditar('lgpd_anonimizacao', recurso='usuario', recurso_id=uid,
             detalhe='direito de eliminação (Art. 18)')
    return jsonify(r)


@app.route('/api/admin/lgpd/purgar-auditoria', methods=['POST'])
@admin_required
def api_lgpd_purgar():
    """Retenção: descarta eventos além do prazo. Guardar IP para sempre é acúmulo sem finalidade."""
    dias = (request.json or {}).get('dias')
    removidos = db.purgar_auditoria(dias)
    return jsonify({'removidos': removidos})


@app.route('/api/admin/auditoria', methods=['GET'])
@admin_required
def api_admin_auditoria():
    """
    Consulta da trilha de acesso.

    Restrita a administrador: a trilha diz quem consultou dado de crédito de
    qual cliente, então ela própria é dado sensível. Só leitura — não há rota
    de escrita nem de exclusão, por desenho.
    """
    try:
        limite = min(max(int(request.args.get('limite', 200)), 1), 1000)
    except (TypeError, ValueError):
        limite = 200
    itens = db.listar_acessos(
        limit=limite,
        user_id=request.args.get('user_id') or None,
        evento=request.args.get('evento') or None,
    )
    for i in itens:
        i['evento_rotulo'] = _aud.rotulo(i['evento'])
        i['sensivel'] = _aud.e_sensivel(i['evento'])
    return jsonify({
        'acessos': itens,
        'total_registrado': db.contar_acessos(),
        'eventos': _aud.EVENTOS,
    })


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

@app.route('/login/2fa', methods=['GET', 'POST'])
@limiter.limit("10 per minute; 40 per hour")
def login_2fa():
    """
    Segundo fator. A senha já foi conferida; aqui falta o código.

    O limite de tentativas é a defesa principal: seis dígitos são um milhão de
    combinações, muito para chutar uma vez e pouco para tentativas ilimitadas.
    """
    uid = session.get('totp_pendente')
    if not uid:
        return redirect(url_for('login'))

    # A etapa pendente expira: sessão meio-autenticada esquecida num
    # computador compartilhado é uma senha já validada esperando alguém.
    if _time.time() - float(session.get('totp_desde') or 0) > 300:
        session.pop('totp_pendente', None)
        session.pop('totp_desde', None)
        return redirect(url_for('login'))

    erro = None
    if request.method == 'POST':
        codigo = (request.form.get('codigo') or '').strip()
        est = db.totp_estado(uid)
        u = db.buscar_usuario_id(uid)

        contador = _totp.verificar(est['segredo'], codigo,
                                   contador_minimo=est['contador'] + 1)
        if contador is not None:
            db.totp_registrar_uso(uid, contador)
        else:
            h = _totp.conferir_codigo_backup(codigo, est['backup'])
            if h:
                db.totp_consumir_backup(uid, h)
                _auditar(_aud.LOGIN_2FA_BACKUP, email=u['email'],
                         detalhe=f"{len(est['backup']) - 1} código(s) restante(s)")
            else:
                _auditar(_aud.LOGIN_2FA_FALHOU, email=u['email'], sucesso=False)
                erro = 'Código inválido ou já utilizado.'

        if not erro:
            session.pop('totp_pendente', None)
            session.pop('totp_desde', None)
            login_user(User(u), remember=True)
            _auditar(_aud.LOGIN, email=u['email'], detalhe='com 2FA')
            return redirect(url_for('app_main'))

    return render_template('login_2fa.html', erro=erro)


@app.route('/api/2fa/iniciar', methods=['POST'])
@login_required
def api_2fa_iniciar():
    """
    Gera o segredo e devolve a URI do QR. AINDA NÃO ATIVA — só depois de um
    código válido, senão um erro na leitura do QR trancaria o usuário fora.
    """
    if db.totp_estado(current_user.id)['ativo']:
        return jsonify({'erro': '2FA já está ativo nesta conta.'}), 400
    segredo = _totp.gerar_segredo()
    db.totp_guardar_segredo(current_user.id, segredo)
    return jsonify({
        'segredo': segredo,
        'uri': _totp.uri_provisionamento(segredo, current_user.email),
        'aviso': 'Confirme com um código do aplicativo para ativar.',
    })


@app.route('/api/2fa/confirmar', methods=['POST'])
@login_required
def api_2fa_confirmar():
    """Ativa e devolve os códigos de recuperação — a ÚNICA vez que eles aparecem."""
    est = db.totp_estado(current_user.id)
    if est['ativo']:
        return jsonify({'erro': '2FA já está ativo.'}), 400
    if not est['segredo']:
        return jsonify({'erro': 'Inicie a configuração primeiro.'}), 400

    contador = _totp.verificar(est['segredo'], (request.json or {}).get('codigo'))
    if contador is None:
        return jsonify({'erro': 'Código inválido. Confira o relógio do aparelho.'}), 400

    codigos = _totp.gerar_codigos_backup()
    db.totp_ativar(current_user.id, [_totp.hash_codigo_backup(c) for c in codigos])
    db.totp_registrar_uso(current_user.id, contador)
    _auditar(_aud.DOIS_FATORES_ATIVADO)
    return jsonify({
        'ok': True,
        'codigos_backup': codigos,
        'aviso': ('Guarde estes códigos agora — eles não serão mostrados de '
                  'novo. Cada um vale uma única vez.'),
    })


@app.route('/api/2fa/desativar', methods=['POST'])
@login_required
def api_2fa_desativar():
    """Exige a senha: sessão sequestrada não pode desligar o segundo fator."""
    senha = (request.json or {}).get('senha') or ''
    if not db.verificar_senha(current_user.email, senha):
        _auditar(_aud.DOIS_FATORES_DESATIVADO, sucesso=False,
                 detalhe='senha incorreta')
        return jsonify({'erro': 'Senha incorreta.'}), 403
    db.totp_desativar(current_user.id)
    _auditar(_aud.DOIS_FATORES_DESATIVADO)
    return jsonify({'ok': True})


@app.route('/api/2fa/estado', methods=['GET'])
@login_required
def api_2fa_estado():
    est = db.totp_estado(current_user.id)
    return jsonify({'ativo': est['ativo'],
                    'codigos_backup_restantes': len(est['backup'])})


@app.route('/logout')
@login_required
def logout():
    _auditar(_aud.LOGOUT)
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
    _auditar(_aud.HISTORICO_LIDO, recurso='fazenda', recurso_id=fid,
             detalhe=f'{len(hist)} registro(s)')
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
    _auditar(_aud.PARECERES_LIDOS, recurso='fazenda', recurso_id=fid,
             detalhe=f'{len(itens)} parecer(es)')
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
    _ident = (parecer.get('identificacao') or {})
    _auditar(_aud.PARECER_PDF, recurso='fazenda',
             recurso_id=_ident.get('fazenda') or None,
             detalhe=(parecer.get('conclusao') or {}).get('recomendacao'))
    return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf',
                     as_attachment=True, download_name='parecer_credito.pdf')

# ── Landing page pública ───────────────────────────────────────────────────────
@app.route('/healthz')
def healthz():
    """Sinal mínimo para o balanceador sem expor configuração ou banco."""
    return jsonify({'status': 'ok'})


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

    credito_valor = float(data.get('credito_valor') or 0)
    prazo_credito = int(data.get('prazo_meses') or 0)
    carencia_credito = int(data.get('carencia_meses') or 0)
    juros_credito = float(data.get('juros_aa') or 0)
    if credito_valor > 0:
        if prazo_credito < 1 or prazo_credito > 60:
            return jsonify({'erro': 'O prazo do crédito deve estar entre 1 e 60 meses.'}), 400
        if carencia_credito < 0 or carencia_credito >= prazo_credito:
            return jsonify({'erro': 'A carência deve ser menor que o prazo do crédito.'}), 400
        if juros_credito < 0:
            return jsonify({'erro': 'A taxa de juros não pode ser negativa.'}), 400

    kwargs = {}
    if 'taxa_natalidade' in data:
        kwargs['taxa_natalidade'] = float(data['taxa_natalidade'])
    if 'bois_vendidos' in data:
        kwargs['bois_vendidos'] = float(data['bois_vendidos'])
    if 'bezerros_vendidos' in data:
        kwargs['bezerros_vendidos'] = float(data['bezerros_vendidos'])

    result = classificar(v, **kwargs)
    ind    = calcular_indicadores(v)
    explicacao_classificacao = montar_explicacao_classificacao(result, ind)
    qualidade_dados = analisar_qualidade_dados(v, data)
    documentos_credito = checklist_credito(data, qualidade_dados)

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
        user_id=current_user.id,
        fazenda_id=data.get('fazenda_id') or None,
    )

    # Camada de dados reais: cada classificação fica pendente de revisão humana
    # e só entra no treinamento depois de confirmada pelo analista.
    origem_dados = (data.get('origem_dados') or 'MANUAL').strip().upper()
    if origem_dados not in {'PDF', 'EXCEL', 'MANUAL'}:
        origem_dados = 'MANUAL'
    db.criar_caso_real(
        valores=v,
        classificacao_ml=result['classificacao'],
        confianca=result['confianca'],
        origem=origem_dados,
        arquivo=data.get('arquivo_origem', ''),
        estado=data.get('estado', ''),
        modelo=data.get('modelo', ''),
        fazenda=fazenda,
        municipio=municipio,
        user_id=current_user.id,
        empresa_id=_resolver_empresa_ativa(),
        fazenda_id=data.get('fazenda_id') or None,
        registro_id=registro_id,
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
    #
    # O PESO MÉDIO vem do rebanho declarado, nos DOIS caminhos.
    #
    # Havia dois: quando o analista digitava os oito componentes, a conversão
    # de R$/cab/mês para R$/@ usava o peso médio real; quando não digitava — o
    # caminho normal — usava 11,7 @/cab fixo, herdado de uma compatibilidade
    # retroativa ("mantendo 119 R$/@ para o CICLO_COMPLETO"), não de medição.
    #
    # Peso médio depende da composição, e rebanho com muito animal jovem pesa
    # bem menos. Medido nas duas fazendas reais que temos:
    #
    #     Fazenda 3 Furnas (ADAPEC) .... 9,75 @/cab contra 11,7  → custo −17%
    #     Vale do Coco ................. 9,87 @/cab contra 11,7  → custo −16%
    #
    # Dividir por um número maior que o real infla o denominador e REDUZ o
    # custo por arroba — menos custo, mais caixa, DSCR maior. O erro corria a
    # favor de aprovar.
    _femeas_024 = float(v[0] + v[2] + v[4])
    _machos_024 = float(v[1] + v[3] + v[5])
    _arrobas_rebanho = arrobas_categorias(
        matrizes=float(v[6] + v[8]), bois=float(v[7] + v[9]),
        jovens_f=_femeas_024, jovens_m=_machos_024)
    _total_cabecas = int(sum(v))
    _arrobas_por_cab = (_arrobas_rebanho / _total_cabecas) if _total_cabecas else 0.0

    # ── Nível tecnológico ────────────────────────────────────────────────────
    # O sistema tinha os perfis de custo (média / top) e nenhum critério para
    # escolher entre eles: aplicava sempre `media` e deixava o `top` num botão
    # que o analista clicava no olho. Numa cria isso vale 23% no custo, e custo
    # errado em 23% desloca DSCR e parecer na mesma proporção.
    #
    # A chave é lotação e produtividade, NÃO tamanho de rebanho — ver a
    # justificativa medida no cabeçalho de services/nivel_tecnologico.py. Sem
    # área declarada, o nível fica indefinido e o custo segue o de antes.
    _nivel_tec = _avaliar_nivel(v, data.get('area_pasto_ha'))

    _custo_padrao_ciclo = custo_arroba_padrao(
        result.get('tipo', 'CICLO_COMPLETO'),
        arrobas_por_cabeca=_arrobas_por_cab or None,
        nivel=_nivel_tec['nivel'])
    custo_arroba = float(data.get('custo_arroba') or _custo_padrao_ciclo)
    custo_desembolso = None
    componentes = data.get('custo_componentes') or {}
    desembolso_cab_mes = sum(float(componentes.get(k, 0) or 0) for k, _ in COMPONENTES)
    if desembolso_cab_mes > 0:
        arrobas_rebanho = _arrobas_rebanho
        total_cabecas = _total_cabecas
        # Os dois caminhos de custo — componentes digitados e perfil padrão —
        # precisam aplicar a MESMA separação de custeio e investimento, senão
        # o parecer muda conforme o analista tenha ou não preenchido a tabela.
        _oper_cab_mes = _desembolso_operacional(
            {k: float(componentes.get(k, 0) or 0) for k, _ in COMPONENTES})
        custo_arroba = custo_arroba_de_desembolso(
            _oper_cab_mes, arrobas_rebanho, total_cabecas)
        custo_desembolso = {
            'componentes': {k: float(componentes.get(k, 0) or 0) for k, _ in COMPONENTES},
            'desembolso_cab_mes': round(desembolso_cab_mes, 2),
            'operacional_cab_mes': round(_oper_cab_mes, 2),
            'investimento_cab_mes': round(desembolso_cab_mes - _oper_cab_mes, 2),
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
    # ── O que o analista pode corrigir na PROJEÇÃO ───────────────────────────
    #
    # O analista já podia sobrescrever custo, natalidade, mortalidade e desmama
    # — tudo do lado do CUSTO. Do lado do VOLUME, não podia nada: a taxa de
    # venda de bezerras e o descarte de matrizes vinham fixos de
    # PARAMS_POR_CICLO e só eram ajustáveis pela rota de cenários, que não é a
    # que emite parecer.
    #
    # Isso importa porque é justamente o volume que está errado hoje na cria: a
    # projeção vende 735 bezerros por ano num rebanho que desmama 362 — o dobro
    # do que produz — e o plantel derrete 61% em cinco anos. Sem este campo, o
    # analista via o DSCR dos anos 2+ despencar e não tinha como corrigir.
    #
    # Não é o conserto do modelo: é dar ao analista o controle do número que
    # ele conhece melhor que a projeção. Quem lê a ficha sabe quantas bezerras
    # aquela fazenda retém.
    _venda_bez = _opt_float(data.get('venda_bez_pct'))
    _desc_mat  = _opt_float(data.get('desc_mat_pct'))
    # O GMD manda na DURAÇÃO da engorda, e a duração manda em quantos giros o
    # lote faz por ano — ver a derivação em simular_cenario. Era 90 dias fixos,
    # que implicavam 1,28 kg/dia e quatro giros.
    _gmd = _opt_float(data.get('ganho_peso_kg_dia'))
    _sim_volume = {}
    if _gmd is not None and _gmd > 0:
        _sim_volume['ganho_peso_kg_dia'] = float(_gmd)
    elif _nivel_tec.get('nivel') and _nivel_tec['nivel'] != 'indefinido':
        # O nível deixa de mexer só no custo e passa a mexer na PRODUÇÃO. Um
        # extensivo ganha 0,45 kg/dia (abate aos 32–36 meses), não os 0,85 do
        # precoce que era o default de todo mundo. Ver GMD_POR_NIVEL.
        _sim_volume['ganho_peso_kg_dia'] = _gmd_do_nivel(_nivel_tec['nivel'])

    # ── Os índices reprodutivos que a ficha coleta e a projeção ignorava ─────
    #
    # Prenhez, natalidade, desmama e mortalidade estavam na tela desde o
    # começo. Eram comparadas com cinco fontes no painel nacional e com o
    # benchmark regional — e NENHUMA entrava na simulação, que rodava sempre
    # com os defaults de PARAMS_POR_CICLO. A analista podia digitar 90% de
    # prenhez e o fluxo de caixa não mexia um centavo.
    #
    # A ordem de precedência é da medição mais direta para a mais derivada:
    #   1. natalidade declarada — é o que a projeção consome
    #   2. prenhez declarada — convertida por perda gestacional medida (6,6%)
    #   3. default do ciclo
    #
    # A desmama declarada entra separada porque é o FIM da cadeia: quando
    # existe, ela vence natalidade e mortalidade juntas (Vieira et al. 2005).
    _nat_decl  = _opt_float(data.get('natalidade_pct'))
    _prenh_decl = _opt_float(data.get('taxa_prenhez_pct'))
    if _nat_decl is not None and _nat_decl > 0:
        _sim_volume['nat_pct'] = max(0.0, min(_nat_decl, 100.0))
    elif _prenh_decl is not None and _prenh_decl > 0:
        _sim_volume['nat_pct'] = max(
            0.0, min(natalidade_de_prenhez(_prenh_decl), 100.0))
    _desm_decl = _opt_float(data.get('desmama_pct'))
    if _desm_decl is not None and _desm_decl > 0:
        _sim_volume['desmama_pct'] = max(0.0, min(_desm_decl, 100.0))
    _mort_decl = _opt_float(data.get('mortalidade_pct'))
    if _mort_decl is not None and _mort_decl > 0:
        _sim_volume['mort_pct'] = max(0.0, min(_mort_decl, 50.0))
    if _venda_bez is not None:
        _sim_volume['venda_bez_pct'] = max(0.0, min(float(_venda_bez), 100.0))
    if _desc_mat is not None:
        _sim_volume['desc_pct'] = max(0.0, min(float(_desc_mat), 100.0))

    _cx = simular_cenario(
        v, 'conservador', ciclo=result['tipo'],
        preco_arroba=preco_boi or float(data.get('preco', 320)),
        custo_arroba=custo_arroba,
        **_sim_volume,
        custo_arroba_cria=_custo_fase('custo_arroba_cria'),
        custo_arroba_recria=_custo_fase('custo_arroba_recria'),
        custo_arroba_engorda=_custo_fase('custo_arroba_engorda'),
        preco_boi_arr=preco_boi, preco_vaca_arr=preco_vaca,
        preco_bezerra_cab=preco_bezerra, preco_bezerro_cab=preco_bezerro)

    # O breakeven apresentado no parecer deve ser o da simulação efetiva,
    # com os índices, custos, preços e parâmetros informados pelo analista.
    # Antes ele era calculado acima, por `calcular_breakeven_simples`, usando
    # defaults fixos e podendo divergir do fluxo de caixa que acabamos de
    # projetar. Mantemos o cálculo simples somente como fallback defensivo.
    _be_sim = _cx.get('preco_breakeven')
    _be_unidade_sim = _cx.get('preco_breakeven_unidade')
    if _be_sim is not None and float(_be_sim) >= 0:
        breakeven = {
            'preco_breakeven': round(float(_be_sim), 2),
            'unidade': _be_unidade_sim or 'R$/arroba',
            'origem': 'simulacao_cenario',
        }
    geracao_caixa_anual = _cx['anos'][0]['resultado']

    # ── Desfrute PROJETADO pela própria simulação ────────────────────────────
    # O sistema calculava o desfrute implicitamente (pelas vendas do ano 1) mas
    # nunca o confrontava com a própria referência: `desfrute` só entrava no
    # painel se o analista o digitasse à mão. Uma projeção que vende o dobro do
    # normal passava sem alarme e inflava o DSCR.
    #
    # Aqui ele é calculado e devolvido ao painel de benchmarks, que já sabe
    # avaliar por modalidade (CRIA 18–30%, CICLO_COMPLETO 20–40%, etc.).
    #
    # Desde a revisão de julho/2026 o desfrute é calculado nas DUAS formas. A
    # simplificada (vendas ÷ rebanho) segue sendo a comparada com as faixas,
    # porque é a base delas e a da ficha de referência. A real desconta compras
    # e variação de estoque, e é a única que separa "vendeu a produção" de
    # "vendeu o plantel" — ver `calcular_desfrute` em benchmarks_nacionais.
    _ano1_desf   = _cx['anos'][0]
    _vend_ano1   = (_ano1_desf.get('vendidos', 0)
                    + _ano1_desf.get('matrizes_descartadas', 0))
    desfrute = calcular_desfrute(
        vendas=_vend_ano1,
        estoque_inicial=sum(v),
        estoque_final=_ano1_desf.get('total'),
        compras=_ano1_desf.get('compras', 0),
    )
    desfrute_projetado = desfrute['simplificado']
    alerta_desfrute = alerta_liquidacao(result['tipo'], desfrute)
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
    _cronograma_nova = cronograma_price(
        credito_valor, juros_credito, prazo_credito, carencia_credito
    ) if credito_valor > 0 else {'parcela_mensal': 0.0, 'anos': []}
    _parcela_nova = _cronograma_nova['parcela_mensal']

    def _servico_nova_no_ano(ano):
        item = next((x for x in _cronograma_nova['anos']
                     if x['ano'] == ano), None)
        return float(item['servico_nova_operacao']) if item else 0.0

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
    _servico_gep = (_servico_nova_no_ano(1)
                    + 12 * endividamento['parcela_existente_mensal'])
    fluxo_gep = calculate_economic_result(
        {'receita_total': _ano1['receita']},
        {
            'custo_manutencao': float(_ano1.get('custo_manutencao', 0.0) or 0.0),
            'custo_reposicao': float(_ano1.get('custo_reposicao', 0.0) or 0.0),
            'custo_operacional': float(_ano1.get('custo', 0.0) or 0.0),
            'reposicao_reprodutores': float(_reposicao_reprodutores or 0.0),
            'servico_divida_anual': float(_servico_gep or 0.0),
            'valor_rebanho_ini': float(_val_ini_cmp['valor_total']),
            'valor_rebanho_fim': float(_val_fim['valor_total']),
        },
        inventory_change=float(_val_fim['valor_total'] - _val_ini_cmp['valor_total']),
    )
    # Decomposição auditável do custo do primeiro ano. O custo operacional
    # continua sendo o desembolso completo (manutenção + reposição de animais)
    # usado pelo caixa e pelo DSCR; estes campos apenas tornam explícita a
    # parcela que costuma empurrar a recria para o negativo.
    fluxo_gep['custo_manutencao'] = round(float(_ano1.get('custo_manutencao', 0.0) or 0.0), 2)
    fluxo_gep['custo_reposicao'] = round(float(_ano1.get('custo_reposicao', 0.0) or 0.0), 2)
    fluxo_gep['resultado_antes_reposicao'] = round(
        fluxo_gep['receita_vendas'] - fluxo_gep['custo_manutencao'], 2)

    # COE (R$/@ vendida) = custo_operacional / arrobas_vendidas
    #
    # ── O COE PASSA A SER CALCULADO EM TODOS OS ANOS ─────────────────────────
    #
    # Era calculado só no ano 1 — o mesmo ano que o próprio parecer documenta
    # como enganoso, porque liquida o estoque declarado na ficha. O efeito
    # medido numa cria de 1.775 cabeças:
    #
    #     ano 1 .... R$ 191,17/@   dentro da faixa medida (166–223)
    #     ano 3 .... R$ 292,74/@   +31% acima do teto
    #
    # A recomendação segue o ano crítico desde julho; o benchmark de custo
    # ficou para trás e continuava dizendo "custo dentro da praça" sobre a
    # única safra em que a fazenda vende o que já tinha em estoque.
    #
    # Agora o custo de cada ano é medido, e o parecer usa o do ano que
    # sustenta a recomendação. `coe_por_arroba` segue sendo o do ano 1 para
    # quem já lia esse campo; o do ano crítico entra ao lado.
    def _arrobas_do_ano(_a):
        """Arrobas comercializadas no ano, com o peso de cada categoria."""
        if _ciclo_tipo in ('CRIA', 'CRIA_RECRIA'):
            return (float(_a.get('matrizes_descartadas', 0)) * 15.33
                    + float(_a.get('bezerras_vendidas', 0)) * 6.00
                    + float(_a.get('femeas_excedentes', 0)) * 7.67
                    + float(_a.get('machos_vendidos', 0)) * 6.67)
        if _ciclo_tipo == 'RECRIA':
            # Peso de saída variável: a receita dividida pelo preço efetivo é
            # que devolve as arrobas reais.
            if _preco_boi_ref > 0 and _a.get('receita', 0) > 0:
                _pe = _preco_boi_ref * CENARIOS['conservador']['mods']['preco']
                return _a['receita'] / max(_pe, 1)
            return 0.0
        return (float(_a.get('bois_vendidos', 0)) * 20.53
                + float(_a.get('descarte_matrizes',
                               _a.get('matrizes_descartadas', 0))) * 15.33
                + float(_a.get('bezerras_vendidas', 0)) * 6.00
                + float(_a.get('machos_024_vendidos',
                               _a.get('machos_vendidos', 0))) * 10.67)

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
        # A UF vem do bloco de preço da praça, que já resolveu município → UF.
        # Sem ela o painel de referência cai no primeiro da modalidade, e um
        # produtor de RO era confrontado com Paragominas/PA.
        fluxo_gep['coe_benchmark']     = _avaliar_coe(
            result.get('tipo', 'CICLO_COMPLETO'), _coe_calc,
            uf=(precos_regional or {}).get('uf'))
        fluxo_gep['arrobas_vendidas']  = round(_arrobas_reais, 1)
    else:
        fluxo_gep['coe_por_arroba']   = None
        fluxo_gep['coe_benchmark']    = None
        fluxo_gep['arrobas_vendidas'] = None

    # A produtividade em @/ha/ano só existe agora: depende das arrobas
    # vendidas, que dependem da simulação, que precisou do custo — que é o que
    # o nível decidiu. Por isso ela entra como CONFERÊNCIA e não reclassifica:
    # um parecer cujo custo não corresponde ao nível exibido seria pior que
    # nenhum nível.
    _nivel_tec = _conferir_produtividade(
        _nivel_tec, fluxo_gep.get('arrobas_vendidas'))
    _nivel_tec['perfil_custo'] = _perfil_do_nivel(_nivel_tec['nivel'])
    result['nivel_tecnologico'] = _nivel_tec

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
    # ── A sensibilidade tem de olhar o MESMO ano que a conclusão ─────────────
    #
    # Ela era calculada no ano 1 enquanto a recomendação segue o ano crítico —
    # e os dois apareciam no mesmo parecer. Medido numa cria de 1.775 cabeças:
    # a conclusão dizia DSCR -0,05 e a linha de preço atual da tabela de
    # sensibilidade dizia 0,88. Quase um ponto de diferença, no mesmo
    # documento, e o analista lê os dois.
    #
    # O ano 1 é justamente o que este sistema documenta como enganoso: ele
    # liquida o estoque declarado na ficha. Testar a resiliência a queda de
    # preço na única safra em que a fazenda vende o que já tinha é testar o
    # ano errado.
    def _idx_ano_critico(_cenario_anos):
        """Índice do pior ano dentro do prazo, pela mesma regra do parecer."""
        _n = max(1, min(-(-int(data.get('prazo_meses', 12) or 12) // 12),
                        len(_cenario_anos)))
        _pior, _menor = 0, None
        for _i, _a in enumerate(_cenario_anos[:_n]):
            _gc = _a['resultado'] - _reposicao_reprodutores
            if _menor is None or _gc < _menor:
                _pior, _menor = _i, _gc
        return _pior

    _i_crit = _idx_ano_critico(_cx['anos'])
    _servico_base = (_servico_nova_no_ano(_i_crit + 1)
                     + 12 * endividamento['parcela_existente_mensal'])
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
            # A sensibilidade tem de partir do MESMO rebanho projetado, senão
            # compara duas fazendas diferentes e o delta deixa de ser do preço.
            **_sim_volume,
        )
        _gc_s = _cx_s['anos'][_i_crit]['resultado'] - _reposicao_reprodutores
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
            **_sim_volume,
        )
        _gc_c = _cx_c['anos'][_i_crit]['resultado'] - _reposicao_reprodutores
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

    # SHAP — explicabilidade técnica para governança e revisão humana.
    # Por padrão NÃO é calculado aqui: são ~160 MB de pico que coincidiam com
    # a classificação e estouravam a memória do contêiner. O frontend busca em
    # /api/shap e funde no parecer, então o PDF continua com os fatores.
    _shap_ctx = {
        'valores':        list(v),
        'tipo':           result['tipo'],
        'origem_decisao': result.get('origem_decisao', 'ml'),
        'regra_aplicada': result.get('regra_aplicada'),
    }
    shap_explicacao = _calcular_shap(**_shap_ctx) if _SHAP_INLINE else {}

    # ── Projeção multianual (conservador, 5 anos) ────────────────────────────
    # Cada ano: receita, custo, resultado, margem%, DSCR (se houver crédito),
    # rebanho, e sinalização de viabilidade para o analista.
    # ── Arroba PRODUZIDA, ao lado da vendida ────────────────────────────────
    #
    # O benchmark EXAGRO e a Tabela 3.7 definem custo por arroba sobre a arroba
    # PRODUZIDA, não a vendida:
    #
    #     @ produzidas = (estoque final − estoque inicial) + (vendas − compras)
    #
    # UMA HIPÓTESE MINHA QUE A MEDIÇÃO DESMENTIU. Eu disse que, em rebanho que
    # cresce, produzida > vendida, e portanto o nosso COE por arroba estaria
    # SUPERESTIMADO — que parte do "+31% acima da faixa" seria só denominador.
    #
    # É o contrário. Medido na cria de 1.775 cabeças, o estoque em arrobas
    # ENCOLHE todo ano, e o custo por arroba produzida fica 16 a 31% ACIMA do
    # custo por arroba vendida, não abaixo:
    #
    #     ano   @ vendidas   Δ estoque   @ produzidas   COE/vend   COE/prod
    #      1        6.134      −3.653          2.482     168,35     416,16
    #      3        3.607        −741          2.866     234,56     295,22
    #      5        3.316        −752          2.564     229,28     296,55
    #
    # POR QUE NÃO TROCAMOS A MÉTRICA PRINCIPAL: no ano 1 a razão explode
    # (+147%), porque é o ano que liquida o estoque declarado. Uma fazenda que
    # vende mais do que produz tem produção tendendo a zero, e o custo por
    # arroba produzida tende ao infinito — número inútil para comparar com
    # painel, e instável justamente onde mais se olha.
    #
    # O QUE ELA É DE FATO, E POR ISSO ENTRA: um detector de liquidação. Quando
    # a produção fica bem abaixo da venda, a fazenda está vendendo ESTOQUE, não
    # safra. `calcular_desfrute` já faz isso em cabeças; aqui é em arroba, que
    # é a unidade em que o crédito raciocina.
    def _estoque_arrobas(_a):
        return arrobas_categorias(
            matrizes=float(_a.get('matrizes', 0) or 0),
            bois=float(_a.get('bois_fim', 0) or 0),
            jovens_f=float(_a.get('jovens_f_fim', 0) or 0),
            jovens_m=float(_a.get('jovens_m_fim', 0) or 0))

    _est_ant = arrobas_categorias(
        matrizes=float(v[6] + v[8]), bois=float(v[9]),
        jovens_f=float(v[0] + v[2] + v[4]),
        jovens_m=float(v[1] + v[3] + v[5] + v[7]))

    # ── A ficha sustenta a reposição que a manutenção do plantel exige? ──────
    #
    # Embrapa-CPATSA (1985) estima 15% de descarte anual como o necessário para
    # MANTER o nível de produtividade; o painel do Pantanal mede 14%. Nós
    # projetamos com 10%, e não subimos o default de propósito: descartar mais
    # sobe a receita e derrete o plantel quando a ficha não tem novilha —
    # vender a matriz para pagar a parcela é o pior motivo possível para um
    # DSCR melhorar.
    #
    # O requisito entra aqui, onde ele é informação em vez de alavanca: quantas
    # novilhas a ficha tem contra quantas matrizes saem por ano.
    _reposicao = _avaliar_reposicao(
        matrizes=float(v[6] + v[8]), novilhas=float(v[4]),
        descarte_pct=_sim_volume.get('desc_pct',
                                     PARAMS_POR_CICLO.get(_ciclo_tipo, {}).get('desc_mat_pct', 10.0)),
        mortalidade_pct=_sim_volume.get('mort_pct', 3.0))

    _projecao_anos = []
    for _ano in _cx['anos']:
        _gc_ano = _ano['resultado'] - _reposicao_reprodutores
        _margem = round(_gc_ano / max(_ano['custo'], 1) * 100, 1)
        _servico_ano = (_servico_nova_no_ano(_ano['ano'])
                        + 12 * endividamento['parcela_existente_mensal'])
        _dscr_ano = round(_gc_ano / _servico_ano, 2) if _servico_ano > 0 else None
        # COE do ANO — é ele que o parecer usa quando o ano crítico não é o
        # primeiro. Ver a nota em `_arrobas_do_ano`.
        _arr_ano = _arrobas_do_ano(_ano)
        _coe_ano = round(_ano['custo'] / _arr_ano, 2) if _arr_ano > 0 else None
        _est_fim = _estoque_arrobas(_ano)
        _arr_prod = _arr_ano + (_est_fim - _est_ant)
        _est_ant = _est_fim
        _projecao_anos.append({
            'ano':         _ano['ano'],
            'receita':     round(_ano['receita'], 2),
            'custo':       round(_ano['custo'], 2),
            'arrobas_vendidas': round(_arr_ano, 1) if _arr_ano > 0 else None,
            # Definição EXAGRO / Tabela 3.7. Pode ser NEGATIVA — e quando é, a
            # fazenda encolheu em arroba no ano: vendeu mais do que produziu.
            'arrobas_produzidas': round(_arr_prod, 1),
            'producao_sobre_venda_pct': (round(_arr_prod / _arr_ano * 100, 1)
                                         if _arr_ano > 0 else None),
            'coe_por_arroba':   _coe_ano,
            'coe_benchmark':    (_avaliar_coe(_ciclo_tipo, _coe_ano,
                                              uf=(precos_regional or {}).get('uf'))
                                 if _coe_ano else None),
            # Custo sobre a receita do próprio ano: métrica imune ao ano de
            # referência e ao perímetro, porque numerador e denominador andam
            # juntos com o preço. É a que o ebook Campo Futuro publica.
            'coe_sobre_receita_pct': (round(_ano['custo'] / _ano['receita'] * 100, 1)
                                      if _ano.get('receita') else None),
            'resultado':   round(_gc_ano, 2),
            'margem_pct':  _margem,
            'rebanho':     _ano.get('total', 0),
            'matrizes':    _ano.get('matrizes', 0),
            'vendidos':    _ano.get('vendidos', 0),
            'dscr':        _dscr_ano,
            'servico_divida_anual': round(_servico_ano, 2),
            'viavel':      (_dscr_ano is None or _dscr_ano >= 1.0) and _gc_ano > 0,
        })

    validacoes_zootecnicas = analisar_validacoes_zootecnicas(
        v, data, projecao=_projecao_anos)
    _parametros_cenarios = dict(_sim_volume)
    _parametros_cenarios.update({
        'preco_arroba': preco_boi or float(data.get('preco', 320)),
        'custo_arroba': custo_arroba,
        'custo_arroba_cria': _custo_fase('custo_arroba_cria'),
        'custo_arroba_recria': _custo_fase('custo_arroba_recria'),
        'custo_arroba_engorda': _custo_fase('custo_arroba_engorda'),
        'preco_boi_arr': preco_boi,
        'preco_vaca_arr': preco_vaca,
        'preco_bezerra_cab': preco_bezerra,
        'preco_bezerro_cab': preco_bezerro,
    })
    comparacao_cenarios = comparar_cenarios(
        v, result['tipo'], parametros=_parametros_cenarios)

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

    # As três perguntas do crédito ficam explícitas e independentes no
    # resultado. Uma operação pode ter caixa suficiente, mas garantia fraca;
    # ou garantia boa, mas inconsistência cadastral. O comitê não deve receber
    # isso escondido numa recomendação única.
    _conclusao = parecer.get('conclusao', {})
    _dscr = _conclusao.get('dscr')
    _cap_recomendacao = _conclusao.get('recomendacao')
    _cap_status = ('aprovada' if _cap_recomendacao == 'aprovar'
                   else 'ressalva' if _cap_recomendacao == 'ressalva'
                   else 'reprovada')
    _cons_score = float(consistencia.get('score_consistencia', 0) or 0)
    _conf = float(result.get('confianca', 0) or 0)
    _risco_alertas = int((consistencia.get('resumo') or {}).get('alertas', 0) or 0)
    _risco_erros = int((consistencia.get('resumo') or {}).get('erros', 0) or 0)
    _risco_status = ('baixo' if _risco_erros == 0 and _risco_alertas <= 1
                     and _cons_score >= 80 and _conf >= 0.70
                     else 'alto' if _risco_erros > 0 or _cons_score < 50
                     else 'medio')
    analises_credito = {
        'capacidade_pagamento': {
            'status': _cap_status,
            'dscr': _dscr,
            'geracao_caixa_anual': round(float(geracao_caixa_anual), 2),
            'capacidade_maxima': _conclusao.get('capacidade_maxima'),
            'justificativa': _conclusao.get('justificativa'),
        },
        'risco_credito': {
            'status': _risco_status,
            'score_consistencia': round(_cons_score, 1),
            'confianca_classificacao': round(_conf, 4),
            'alertas_consistencia': _risco_alertas,
            'erros_consistencia': _risco_erros,
            'tipo_exploracao': result.get('tipo'),
        },
        'garantia': {
            'status': garantia.get('veredito', 'nao_avaliada'),
            'valor_mercado': garantia.get('valor_mercado'),
            'valor_execucao': garantia.get('valor_execucao'),
            'ltv': garantia.get('ltv'),
            'credito_solicitado': garantia.get('credito_solicitado'),
            'justificativa': garantia.get('justificativa'),
        },
    }
    parecer['analises_credito'] = analises_credito
    parecer['qualidade_dados'] = qualidade_dados
    parecer['explicacao_classificacao'] = explicacao_classificacao
    parecer['validacoes_zootecnicas'] = validacoes_zootecnicas
    parecer['comparacao_cenarios'] = comparacao_cenarios
    parecer['documentos_credito'] = documentos_credito
    fluxo_mensal = projetar_fluxo_mensal(_projecao_anos)
    parecer['fluxo_mensal'] = fluxo_mensal
    rating = calcular_rating(
        dscr=_conclusao.get('dscr_minimo', _conclusao.get('dscr')),
        ltv=garantia.get('ltv'),
        consistencia=consistencia.get('score_consistencia', 0),
        confianca=qualidade_dados.get('nivel_confianca', 'media-baixa'),
        documentos_pendentes=len(documentos_credito.get('pendentes', [])),
        comprometimento_pct=endividamento.get('comprometimento_pct'))
    parecer['rating'] = rating
    # Nível operacional: uma aprovação matemática com documentos faltantes
    # vira aprovação condicionada, nunca aprovação final.
    _rec_base = _conclusao.get('recomendacao')
    _docs_pendentes_obrig = any(
        x.get('obrigatorio') for x in documentos_credito.get('pendentes', []))
    if not _rec_base:
        _nivel_rec, _rotulo_rec = 'sem_credito_informado', 'SEM CRÉDITO INFORMADO'
    elif _rec_base == 'aprovar' and _docs_pendentes_obrig:
        _nivel_rec, _rotulo_rec = (
            'aprovacao_condicionada', 'APROVAÇÃO CONDICIONADA À DOCUMENTAÇÃO')
    elif _rec_base == 'aprovar':
        _nivel_rec, _rotulo_rec = 'pre_aprovado', 'PRÉ-APROVADO'
    elif _rec_base == 'ressalva':
        _nivel_rec, _rotulo_rec = 'revisao_com_ressalvas', 'REVISÃO COM RESSALVAS'
    else:
        _nivel_rec, _rotulo_rec = 'nao_recomendado', 'NÃO RECOMENDADO'
    parecer['conclusao']['nivel_recomendacao'] = _nivel_rec
    parecer['conclusao']['nivel_recomendacao_label'] = _rotulo_rec

    # Persiste no histórico da fazenda apenas quando há fazenda e solicitação.
    fazenda_id = data.get('fazenda_id')
    if fazenda_id and data.get('credito_valor'):
        empresa_id = _resolver_empresa_ativa()
        if empresa_id and db.buscar_fazenda(int(fazenda_id), empresa_id):
            db.salvar_parecer(current_user.id, int(fazenda_id),
                              solicitacao=credito_inputs, parecer=parecer)

    # Fecha o par do acervo: o que o parser leu × o que o analista de fato
    # usou. É esta metade que ensina — o documento sozinho é depósito, o par é
    # rótulo humano dizendo em qual faixa o parser tropeça. A fila de
    # divergências é o que vira fixture das agências sem documento real.
    _doc_id = data.get('documento_id')
    if _doc_id:
        try:
            _doc = db.documento_parse(int(_doc_id), _resolver_empresa_ativa())
            if _doc is not None:
                _cmp = doc_comparar(_doc, list(v))
                db.registrar_correcao(int(_doc_id), list(v), _cmp,
                                      fazenda_id=fazenda_id or None)
        except Exception as e:
            logger.error(f'Falha ao registrar correção do documento: {e}',
                         exc_info=True)

    # A trilha registra a REFERÊNCIA, não o rebanho: duplicar o dado numa
    # segunda tabela só multiplicaria a superfície de vazamento do que se quer
    # proteger. O conteúdo já está em `pareceres` e `registros`.
    _auditar(_aud.PARECER_GERADO,
             recurso='fazenda', recurso_id=fazenda_id or (fazenda or None),
             detalhe=f"{result.get('tipo')} · "
                     f"{(parecer.get('conclusao') or {}).get('recomendacao') or 'sem crédito'}")

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

    response_payload = {
        **result,
        'indicadores': ind,
        'qualidade_dados': qualidade_dados,
        'explicacao_classificacao': explicacao_classificacao,
        'validacoes_zootecnicas': validacoes_zootecnicas,
        'comparacao_cenarios': comparacao_cenarios,
        'documentos_credito': documentos_credito,
        'fluxo_mensal': fluxo_mensal,
        'rating': rating,
        'indicadores_benchmark': ind_bench,
        'benchmarks': benchmarks,
        'benchmarks_nacionais': painel_nacional,
        'avaliacao_embrapa': avaliacao_embrapa,
        'ciclo_info': ciclo_info,
        'breakeven_simples': breakeven,
        'consistencia': consistencia,
        'parecer': parecer,
        'analises_credito': analises_credito,
        'fluxo_gep': fluxo_gep,
        'sensibilidade': sensibilidade,
        'sensibilidade_custo': sensibilidade_custo,
        'custo_desembolso': custo_desembolso,
        'valores': v,
        'registro_id': registro_id,
        'shap_explicacao': shap_explicacao,
        'projecao_anos': _projecao_anos,
        'reposicao_plantel': _reposicao,
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
            # Desfrute real (literatura): desconta compras e variação de
            # estoque. É o que separa venda de produção de venda de plantel.
            'real':          desfrute['real'],
            'afastamento':   desfrute['afastamento'],
            'liquidacao':    alerta_desfrute,
        },
        'shap_pendente':  not _SHAP_INLINE,
        'shap_contexto':  _shap_ctx if not _SHAP_INLINE else None,
        'narrativa_pendente': (not _NARRATIVA_INLINE) and _narrativa_ativa(),
        'narrativa_contexto': _ctx_narrativa if not _NARRATIVA_INLINE else None,
    }

    try:
        organization_id = _resolver_empresa_ativa()
        if organization_id:
            analysis_pipeline_result = run_full_analysis(
                data,
                {
                    'organization_id': organization_id,
                    'user_id': current_user.id,
                },
            )
            db.save_analysis_snapshot(
                organization_id=organization_id,
                user_id=current_user.id,
                payload=data,
                context={
                    'organization_id': organization_id,
                    'user_id': current_user.id,
                },
                result=analysis_pipeline_result,
                version=analysis_pipeline_result.get('version'),
            )
    except Exception as e:
        logger.warning(f'Falha ao salvar snapshot da análise: {e}')

    return jsonify(response_payload)


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
    caso_real = db.buscar_caso_real(int(registro_id), user_id=current_user.id)
    if caso_real:
        db.confirmar_caso_real(
            caso_real['id'], ciclo,
            user_id=current_user.id,
            empresa_id=_resolver_empresa_ativa(),
        )
    concordou = registro.get('class_ml') == ciclo
    _auditar(_aud.CICLO_CONFIRMADO, recurso='registro', recurso_id=registro_id,
             detalhe=f'ML={registro.get("class_ml")} analista={ciclo}')
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


@app.route('/api/casos-reais', methods=['GET'])
@login_required
def api_listar_casos_reais():
    """Lista classificações aguardando revisão ou já rotuladas pelo analista."""
    status = (request.args.get('status') or '').strip().upper() or None
    classificacao = (request.args.get('classificacao') or '').strip().upper() or None
    origem = (request.args.get('origem') or '').strip().upper() or None
    try:
        limit = int(request.args.get('limit') or 100)
    except (TypeError, ValueError):
        return jsonify({'erro': 'limit deve ser numérico.'}), 400
    if status and status not in db._CASOS_STATUS:
        return jsonify({'erro': 'status inválido.'}), 400
    if classificacao and classificacao not in db._CASOS_TIPOS:
        return jsonify({'erro': 'classificação inválida.'}), 400
    if origem and origem not in db._CASOS_ORIGENS:
        return jsonify({'erro': 'origem inválida.'}), 400
    empresa_id = _resolver_empresa_ativa()
    return jsonify({'casos': db.listar_casos_reais(
        user_id=current_user.id, empresa_id=empresa_id, status=status,
        classificacao=classificacao, origem=origem, limit=limit,
    )})


@app.route('/api/casos-reais/resumo', methods=['GET'])
@login_required
def api_resumo_casos_reais():
    return jsonify(db.resumo_casos_reais(
        user_id=current_user.id, empresa_id=_resolver_empresa_ativa()))


@app.route('/api/casos-reais/<int:caso_id>/confirmar', methods=['POST'])
@login_required
def api_confirmar_caso_real(caso_id):
    data = request.json or {}
    ciclo = (data.get('classificacao') or data.get('ciclo') or '').strip().upper()
    try:
        caso = db.confirmar_caso_real(
            caso_id, ciclo, observacao=data.get('observacao', ''),
            user_id=current_user.id, empresa_id=_resolver_empresa_ativa())
    except (ValueError, LookupError) as exc:
        return jsonify({'erro': str(exc)}), 400 if isinstance(exc, ValueError) else 404
    if caso.get('registro_id'):
        db.confirmar(caso['registro_id'], ciclo)
    return jsonify({'ok': True, 'caso': caso})


@app.route('/api/casos-reais/<int:caso_id>/descartar', methods=['POST'])
@login_required
def api_descartar_caso_real(caso_id):
    data = request.json or {}
    try:
        db.descartar_caso_real(
            caso_id, data.get('motivo', ''), user_id=current_user.id,
            empresa_id=_resolver_empresa_ativa())
    except (ValueError, LookupError) as exc:
        return jsonify({'erro': str(exc)}), 400 if isinstance(exc, ValueError) else 404
    return jsonify({'ok': True, 'caso_id': caso_id, 'status': 'DESCARTADO'})


@app.route('/api/shap', methods=['POST'])
@login_required
def api_shap():
    """
    Fatores SHAP da classificação, fora do caminho crítico.

    Separado de /api/classificar por MEMÓRIA, não por latência: construir os
    TreeExplainer dos quatro estimadores aloca ~160 MB, e esse pico somado ao
    da classificação estourava o contêiner (502). Aqui ele acontece sozinho.

    O frontend chama logo após renderizar o resultado e funde a resposta no
    parecer — a explicabilidade técnica continua no PDF.
    """
    ctx = (request.json or {}).get('contexto') or {}
    valores = ctx.get('valores')
    tipo = ctx.get('tipo')
    if not valores or not tipo:
        return jsonify({'erro': 'Contexto da classificação ausente.'}), 400
    try:
        valores = [int(x or 0) for x in valores][:10]
    except (TypeError, ValueError):
        return jsonify({'erro': 'Valores inválidos.'}), 400
    if len(valores) != 10:
        return jsonify({'erro': 'Esperados 10 valores de rebanho.'}), 400

    return jsonify({'shap_explicacao': _calcular_shap(
        valores, tipo,
        origem_decisao=ctx.get('origem_decisao') or 'ml',
        regra_aplicada=ctx.get('regra_aplicada'),
    )})


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
    """Chat do assistente de crédito."""
    from services.groq_narrativa import gerar_resposta_chat, _feature_ativa

    data = request.json or {}
    mensagem = (data.get('mensagem') or '').strip()
    if not mensagem:
        return jsonify({'erro': 'Mensagem vazia'}), 400
    if len(mensagem) > 800:
        return jsonify({'erro': 'Mensagem muito longa (máx. 800 caracteres)'}), 400

    # Conceito e recusa vêm ANTES do modelo, e sem depender dele.
    #
    # Conceito porque a explicação tem de bater com o CÁLCULO: um modelo
    # explica deságio em geral, nós explicamos o deságio que o parecer aplica.
    #
    # Recusa porque prompt é pedido, não garantia. Taxa de Pronaf, prazo de
    # Moderfrota, exigência do MCR — o modelo responde com confiança e erra, e
    # informação errada sobre condição de crédito custa caro numa proposta.
    # Classificar antes de chamar é o que torna a recusa uma propriedade do
    # sistema e não uma esperança sobre o modelo.
    _direto = _assistente.responder(mensagem)
    if _direto is not None:
        return jsonify({'resposta': _direto['texto'], 'origem': _direto['tipo']})

    if not _feature_ativa():
        return jsonify({'erro': 'IA não configurada — adicione GROQ_API_KEY nas variáveis de ambiente.'}), 503

    historico = data.get('historico') or []
    contexto  = data.get('contexto') or {}

    resposta = gerar_resposta_chat(mensagem, historico, contexto)
    if resposta is None:
        return jsonify({'erro': 'Serviço de IA temporariamente indisponível. Tente novamente.'}), 503

    return jsonify({'resposta': resposta, 'origem': 'modelo'})


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
        return ('Número não vinculado. Entre na Orkavyn Agro Intelligence, gere um código de '
                'vinculação e envie os 6 dígitos aqui.')

    # Mesma disciplina do chat da tela: conceito e recusa não passam pelo
    # modelo, e não dependem de haver parecer emitido. Um analista que ainda
    # não gerou nada continua podendo perguntar como a conta é feita.
    _direto = _assistente.responder(texto)
    if _direto is not None:
        # `_auditar` lê o usuário da sessão, e no webhook não há sessão — o
        # registro vai direto, com o uid que o vínculo do telefone deu.
        try:
            db.registrar_acesso(_aud.WHATSAPP_CONSULTA, user_id=uid,
                                detalhe=f'assistente:{_direto["tipo"]}')
        except Exception:
            logger.exception('[whatsapp] falha ao registrar consulta')
        return _direto['texto']

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
_noticias_refreshing = False
_noticias_lock = threading.Lock()
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


def _atualizar_noticias_em_background() -> None:
    """Atualiza o ticker fora da requisição que abre o painel."""
    global _noticias_cache, _noticias_cache_ts, _noticias_refreshing
    try:
        sess = _session_com_retry()
        todos = []
        for url in _RSS_FEEDS:
            todos.extend(_buscar_rss(url, sess))
        filtrados = _filtrar_agro(todos)[:30]
        if filtrados:
            with _noticias_lock:
                _noticias_cache = filtrados
                _noticias_cache_ts = _time.monotonic()
    finally:
        with _noticias_lock:
            _noticias_refreshing = False


def _solicitar_atualizacao_noticias() -> None:
    global _noticias_refreshing
    with _noticias_lock:
        if _noticias_refreshing:
            return
        _noticias_refreshing = True
    threading.Thread(target=_atualizar_noticias_em_background,
                     name='noticias-rss', daemon=True).start()


def _noticias_fresh() -> list:
    agora = _time.monotonic()
    if _noticias_cache and (agora - _noticias_cache_ts) < _NOTICIAS_TTL:
        return _noticias_cache
    _solicitar_atualizacao_noticias()
    return _noticias_cache or []


@app.route('/api/noticias', methods=['GET'])
@login_required
def api_noticias():
    """Retorna até 30 notícias agropecuárias de RSS público (Canal Rural + G1 Agro).

    Cache de 20 minutos — não bate nos feeds a cada chamada do ticker.
    """
    try:
        itens = _noticias_fresh()
        return jsonify({'ok': True, 'noticias': itens, 'total': len(itens),
                        'atualizando': _noticias_refreshing})
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
        if orig == 'RESUMO_FAZENDAS':
            dados = parsear_resumo_fazendas(text, pdf_path=tmp_path)
        elif orig == 'DECLARACAO_IDARON':
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

        # Guarda o documento e o que o parser extraiu dele. Antes o arquivo era
        # lido e apagado no `finally`, e com ele ia embora a única evidência de
        # como o parser se comportou naquele documento. Ver o cabeçalho de
        # services/documentos.py: três fichas reais acharam três classes de
        # defeito que 64 arquivos de teste sintético não acharam.
        #
        # Nunca derruba a leitura: o analista precisa do parse mesmo que o
        # acervo esteja indisponível. Mesma regra da trilha de auditoria.
        dados['documento_id'] = None
        try:
            _eid = _resolver_empresa_ativa()
            if _eid is not None:
                with open(tmp_path, 'rb') as _fh:
                    _conteudo = _fh.read()
                dados['documento_id'] = db.registrar_documento(
                    empresa_id=_eid,
                    user_id=int(current_user.id),
                    nome_arquivo=f.filename,
                    conteudo=_conteudo,
                    sha256=doc_impressao(_conteudo),
                    origem=orig,
                    parse=dados,
                    valores_lidos=dados.get('valores') or [],
                )
        except Exception as e:
            logger.error(f'Falha ao guardar documento lido: {e}', exc_info=True)

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


@app.route('/api/fichas/importar', methods=['POST'])
@login_required
def api_importar_fichas():
    """Importa um lote de PDFs usando o fluxo baseado no XLSM.

    O endpoint não confirma nem grava a consolidação no cadastro. Ele devolve
    todos os registros, inclusive os pendentes de revisão, para a interface
    confirmar ou corrigir antes de classificar o rebanho.
    """
    arquivos = request.files.getlist('pdf') or request.files.getlist('arquivos')
    arquivos = [arquivo for arquivo in arquivos if arquivo and arquivo.filename]
    if not arquivos:
        return jsonify({
            'sucesso': False,
            'arquivos_processados': 0,
            'fichas_identificadas': 0,
            'animais_extraidos': 0,
            'registros': [],
            'avisos': [],
            'erros': ['Envie um ou mais arquivos no campo "pdf".'],
        }), 400

    estado = (request.form.get('estado') or '').strip() or None
    modelo = (request.form.get('modelo') or '').strip() or None
    todos_registros = []
    avisos = []
    erros = []
    processados = 0
    fichas = 0

    for arquivo in arquivos:
        if not arquivo.filename.lower().endswith('.pdf'):
            erros.append(f'{arquivo.filename}: apenas arquivos PDF são aceitos.')
            continue
        tmp_path = None
        try:
            tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
            tmp_path = tmp.name
            tmp.close()
            arquivo.save(tmp_path)
            leitura = read_ficha_pdf(tmp_path, estado=estado, modelo=modelo)
            processados += 1
            if leitura.get('sucesso'):
                fichas += 1
                origem_leitura = leitura.get('origem', '')
                modelo_leitura = leitura.get('modelo', '')
                for registro in leitura.get('registros') or []:
                    registro = dict(registro)
                    registro.setdefault('origem', origem_leitura)
                    registro.setdefault('modelo', modelo_leitura)
                    todos_registros.append(registro)
                avisos.extend(
                    f'{arquivo.filename}: {aviso}'
                    for aviso in leitura.get('avisos') or []
                )
                erros.extend(
                    f'{arquivo.filename}: {erro}'
                    for erro in leitura.get('erros') or []
                )
            else:
                erros.extend(
                    f'{arquivo.filename}: {erro}'
                    for erro in leitura.get('erros') or ['falha não detalhada']
                )
        except Exception as exc:
            erros.append(f'{arquivo.filename}: {exc}')
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    validacao = validar_registros(todos_registros)
    todos_registros = validacao['registros']
    avisos.extend(validacao['avisos'])
    erros.extend(validacao['erros'])
    consolidado = consolidar_registros(todos_registros)
    valores_agregados = [
        sum((item.get('valores') or [0] * 10)[indice] for item in consolidado)
        for indice in range(10)
    ]
    fazendas_compat = [{
        'fazenda': item.get('fazenda', ''),
        'municipio': item.get('municipio', ''),
        'estado': item.get('estado', ''),
        'origem': item.get('origem', ''),
        'modelo': item.get('modelo', ''),
        'valores': item.get('valores', [0] * 10),
        'total': item.get('total', 0),
    } for item in consolidado]
    animais = sum(
        int(registro['quantidade'])
        for registro in todos_registros
        if isinstance(registro.get('quantidade'), (int, float))
        and registro.get('quantidade') >= 0
        and registro.get('status') == 'Distribuído'
    )
    return jsonify({
        'sucesso': bool(fichas) and not erros,
        'arquivos_processados': processados,
        'fichas_identificadas': fichas,
        'animais_extraidos': animais,
        'registros': todos_registros,
        'log': registros_para_log(todos_registros),
        'consolidado': consolidado,
        # Campos compatíveis com o frontend legado /api/ler-pdf.
        'valores': valores_agregados,
        'fazendas': fazendas_compat,
        'fazenda': (
            fazendas_compat[0]['fazenda'] if len(fazendas_compat) == 1
            else f'{len(fazendas_compat)} fazendas combinadas'
        ),
        'municipio': fazendas_compat[0]['municipio'] if len(fazendas_compat) == 1 else '',
        'total': sum(valores_agregados),
        'avisos': avisos,
        'erros': erros,
        'pode_confirmar': bool(todos_registros) and not erros,
    })


@app.route('/api/ficha/download', methods=['GET'])
@login_required
def api_ficha_download():
    """Baixa a ficha XLSM oficial de classificação do rebanho."""
    return send_file(
        os.path.join(app.static_folder, 'classificacao_rebanho_fichas.xlsm'),
        mimetype='application/vnd.ms-excel.sheet.macroEnabled.12',
        as_attachment=True,
        download_name='classificacao_rebanho_fichas.xlsm',
    )


@app.route('/api/ficha/instrucoes', methods=['GET'])
@login_required
def api_ficha_instrucoes():
    """Baixa o manual rápido de preenchimento da ficha XLSM."""
    return send_from_directory(
        app.static_folder,
        'ficha_classificacao_rebanho_instrucoes.txt',
        as_attachment=True,
        download_name='ficha_classificacao_rebanho_instrucoes.txt',
        mimetype='text/plain; charset=utf-8',
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
        validacao = validar_fazendas_importadas(fazendas)
        if not validacao['valido']:
            return jsonify({'erro': '; '.join(validacao['erros']),
                            'validacao': validacao}), 400
        uf = (request.form.get('uf') or '').strip().upper()
        if uf:
            for faz in fazendas:
                faz.setdefault('uf', uf)
        return jsonify({'fazendas': fazendas, 'total_fazendas': len(fazendas),
                        'validacao': validacao})
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
        if orig == 'RESUMO_FAZENDAS':
            dados = parsear_resumo_fazendas(text)
        elif orig == 'DECLARACAO_IDARON':
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
    logger.info("🚀 Orkavyn Agro Intelligence iniciado em http://localhost:5050")
    app.run(debug=True, port=5050)

