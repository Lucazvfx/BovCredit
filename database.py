"""
Fluxo de Gestão — Camada de persistência
Usa PostgreSQL (via DATABASE_URL) em produção e SQLite localmente.
"""
import json, os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from contextlib import contextmanager


def _sanitizar_database_url(raw: str) -> str:
    """Extrai uma URL Postgres válida de DATABASE_URL.

    Tolera o valor corrompido que o Railway às vezes injeta: várias URLs de
    conexão concatenadas sem separador e referências ``${{...}}`` não
    resolvidas. Retorna '' quando não há URL utilizável (o app cai no SQLite).
    """
    raw = (raw or '').strip()
    if not raw:
        return ''
    # Valor limpo: exatamente uma URL, sem placeholders do Railway.
    if raw.count('://') == 1 and '${' not in raw and '{' not in raw:
        return raw
    # Valor corrompido: pega o primeiro trecho bem-formado (com host e sem
    # placeholder). split() remove o delimitador, então cada parte já fica
    # delimitada pela próxima ocorrência de 'postgresql://'.
    for esquema in ('postgresql://', 'postgres://'):
        for parte in raw.split(esquema):
            parte = parte.strip()
            if '@' in parte and not ({'$', '{', '}'} & set(parte)):
                return esquema + parte
    return ''


_DATABASE_URL = _sanitizar_database_url(os.environ.get('DATABASE_URL', ''))
_USE_PG = bool(_DATABASE_URL)

# ─────────────────────────────────────────────
# BACKENDS
# ─────────────────────────────────────────────
if _USE_PG:
    import psycopg2
    import psycopg2.extras

    @contextmanager
    def get_conn():
        conn = psycopg2.connect(_DATABASE_URL)
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _exec(sql, params=(), fetch=None, commit=False):
        with get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                result = None
                if fetch == 'one':
                    row = cur.fetchone()
                    result = dict(row) if row else None
                elif fetch == 'all':
                    rows = cur.fetchall()
                    result = [dict(r) for r in rows]
                elif fetch == 'lastrow':
                    cur.execute('SELECT lastval()')
                    result = cur.fetchone()['lastval']
                if commit:
                    conn.commit()
                return result

    _PH  = '%s'
    _AI  = 'SERIAL PRIMARY KEY'
    _NOW = 'NOW()'
    _ADD_COL = 'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {tipo}'

else:
    import sqlite3

    _DB_PATH = os.path.join(os.path.dirname(__file__), 'gestao.db')

    @contextmanager
    def get_conn():
        conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _exec(sql, params=(), fetch=None, commit=False):
        with get_conn() as conn:
            cur = conn.execute(sql, params)
            result = None
            if fetch == 'one':
                row = cur.fetchone()
                result = dict(row) if row else None
            elif fetch == 'all':
                rows = cur.fetchall()
                result = [dict(r) for r in rows]
            elif fetch == 'lastrow':
                result = cur.lastrowid
            if commit:
                conn.commit()
            return result

    _PH  = '?'
    _AI  = 'INTEGER PRIMARY KEY AUTOINCREMENT'
    _NOW = "(datetime('now'))"
    _ADD_COL = None   # handled via try/except no SQLite


def _add_column_safe(table, col, tipo):
    """Adiciona coluna ignorando erro se já existir (SQLite não suporta IF NOT EXISTS)."""
    if _USE_PG:
        _exec(_ADD_COL.format(table=table, col=col, tipo=tipo), commit=True)
    else:
        try:
            _exec(f'ALTER TABLE {table} ADD COLUMN {col} {tipo}', commit=True)
        except Exception:
            pass


# ─────────────────────────────────────────────
# MIGRATIONS
# ─────────────────────────────────────────────
def _migrar_usuarios_para_empresas():
    """Garante que todo usuário tenha ao menos uma empresa (idempotente).

    Usuários criados após esta feature já ganham empresa em criar_usuario();
    esta função cobre só quem foi criado antes dela existir.
    """
    ph = _PH
    usuarios_sem_empresa = _exec('''
        SELECT u.id, u.nome, u.nome_consultoria, u.logo_base64 FROM usuarios u
        WHERE NOT EXISTS (SELECT 1 FROM empresa_membros m WHERE m.user_id = u.id)
    ''', fetch='all') or []
    for u in usuarios_sem_empresa:
        nome_empresa = (u.get('nome_consultoria') or '').strip() or f"{u['nome']} — Consultoria"
        eid = _exec(f'INSERT INTO empresas (nome, logo_base64) VALUES ({ph},{ph})',
                    (nome_empresa, u.get('logo_base64') or ''), fetch='lastrow', commit=True)
        _exec(f'INSERT INTO empresa_membros (empresa_id, user_id) VALUES ({ph},{ph})',
              (eid, u['id']), commit=True)
        _exec(f'UPDATE fazendas SET empresa_id={ph} WHERE user_id={ph} AND empresa_id IS NULL',
              (eid, u['id']), commit=True)


# ─────────────────────────────────────────────
# SCHEMA
# ─────────────────────────────────────────────
def init_db():
    # Usuários
    _exec(f'''
        CREATE TABLE IF NOT EXISTS usuarios (
            id         {_AI},
            email      TEXT NOT NULL UNIQUE,
            nome       TEXT NOT NULL,
            senha_hash TEXT NOT NULL,
            plano      TEXT DEFAULT 'free',
            created_at TIMESTAMP DEFAULT {_NOW}
        )
    ''', commit=True)

    # Fazendas
    _exec(f'''
        CREATE TABLE IF NOT EXISTS fazendas (
            id         {_AI},
            user_id    INTEGER NOT NULL,
            nome       TEXT NOT NULL,
            proprietario TEXT DEFAULT '',
            municipio  TEXT DEFAULT '',
            estado     TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT {_NOW}
        )
    ''', commit=True)

    # Classificações
    _exec(f'''
        CREATE TABLE IF NOT EXISTS registros (
            id          {_AI},
            valores     TEXT    NOT NULL,
            class_ml    TEXT    NOT NULL,
            class_conf  TEXT,
            confianca   REAL    DEFAULT 0,
            fazenda     TEXT    DEFAULT '',
            municipio   TEXT    DEFAULT '',
            nat_pct     REAL    DEFAULT 75,
            created_at  TIMESTAMP DEFAULT {_NOW}
        )
    ''', commit=True)

    # Nova Tabela: Histórico de Cotações da Arroba (Agora com Boi China)
    _exec(f'''
        CREATE TABLE IF NOT EXISTS cotacao_arroba (
            id           {_AI},
            data_cotacao DATE UNIQUE,
            preco_boi    REAL,
            preco_vaca   REAL,
            preco_boi_china REAL
        )
    ''', commit=True)

    # KV genérica para contadores e flags (multi-worker safe)
    _exec(f'''
        CREATE TABLE IF NOT EXISTS meta (
            chave  TEXT PRIMARY KEY,
            valor  TEXT NOT NULL
        )
    ''', commit=True)

    # Pareceres de crédito (histórico consultável por fazenda)
    _exec(f'''
        CREATE TABLE IF NOT EXISTS pareceres (
            id           {_AI},
            fazenda_id   INTEGER,
            user_id      INTEGER NOT NULL,
            solicitacao  TEXT,
            parecer      TEXT,
            recomendacao TEXT,
            dscr         REAL,
            created_at   TIMESTAMP DEFAULT {_NOW}
        )
    ''', commit=True)

    # Empresas (consultorias) e vínculo N:N com usuários
    _exec(f'''
        CREATE TABLE IF NOT EXISTS empresas (
            id          {_AI},
            nome        TEXT NOT NULL,
            logo_base64 TEXT DEFAULT '',
            created_at  TIMESTAMP DEFAULT {_NOW}
        )
    ''', commit=True)

    _exec(f'''
        CREATE TABLE IF NOT EXISTS empresa_membros (
            id          {_AI},
            empresa_id  INTEGER NOT NULL,
            user_id     INTEGER NOT NULL,
            created_at  TIMESTAMP DEFAULT {_NOW}
        )
    ''', commit=True)

    # Colunas adicionadas de forma segura (retrocompatibilidade)
    _add_column_safe('registros', 'user_id',    'INTEGER')
    _add_column_safe('registros', 'fazenda_id', 'INTEGER')
    _add_column_safe('cotacao_arroba', 'preco_boi_china', 'REAL')
    _add_column_safe('cotacao_arroba', 'preco_bezerro', 'REAL')
    _add_column_safe('cotacao_arroba', 'preco_bezerra', 'REAL')
    _add_column_safe('usuarios', 'security_question', 'TEXT DEFAULT \'\'')
    _add_column_safe('usuarios', 'security_answer_hash', 'TEXT DEFAULT \'\'')
    _add_column_safe('usuarios', 'nome_consultoria', 'TEXT DEFAULT \'\'')
    _add_column_safe('usuarios', 'logo_base64', 'TEXT DEFAULT \'\'')
    _add_column_safe('fazendas', 'empresa_id', 'INTEGER')

    _migrar_usuarios_para_empresas()


# ─────────────────────────────────────────────
# USUÁRIOS
# ─────────────────────────────────────────────
def criar_usuario(email: str, nome: str, senha: str,
                  security_question: str = '', security_answer: str = '') -> int:
    ph = _PH
    nome = nome.strip()
    rid = _exec(
        f'INSERT INTO usuarios (email, nome, senha_hash, security_question, security_answer_hash) VALUES ({ph},{ph},{ph},{ph},{ph})',
        (email.lower().strip(), nome, generate_password_hash(senha),
         security_question, generate_password_hash(security_answer.lower().strip()) if security_answer else ''),
        fetch='lastrow', commit=True
    )
    uid = int(rid)
    eid = _exec(f'INSERT INTO empresas (nome) VALUES ({ph})',
                (f'{nome} — Consultoria',), fetch='lastrow', commit=True)
    _exec(f'INSERT INTO empresa_membros (empresa_id, user_id) VALUES ({ph},{ph})',
          (eid, uid), commit=True)
    return uid

def empresas_do_usuario(user_id: int) -> list:
    """Empresas às quais o usuário pertence."""
    ph = _PH
    return _exec(f'''SELECT e.id, e.nome, e.logo_base64 FROM empresas e
                     JOIN empresa_membros m ON m.empresa_id = e.id
                     WHERE m.user_id={ph} ORDER BY e.nome''', (user_id,), fetch='all') or []


def usuario_pertence_a_empresa(user_id: int, empresa_id: int) -> bool:
    ph = _PH
    r = _exec(f'SELECT 1 FROM empresa_membros WHERE user_id={ph} AND empresa_id={ph}',
              (user_id, empresa_id), fetch='one')
    return bool(r)


def buscar_empresa(empresa_id: int) -> dict | None:
    ph = _PH
    return _exec(f'SELECT * FROM empresas WHERE id={ph}', (empresa_id,), fetch='one')


def atualizar_perfil_empresa(empresa_id: int, nome: str, logo_base64: str):
    ph = _PH
    _exec(f'UPDATE empresas SET nome={ph}, logo_base64={ph} WHERE id={ph}',
          ((nome or '').strip()[:120], logo_base64 or '', empresa_id), commit=True)

def resetar_senha(email: str, nova_senha: str):
    ph = _PH
    _exec(f'UPDATE usuarios SET senha_hash={ph} WHERE email={ph}',
          (generate_password_hash(nova_senha), email.lower().strip()), commit=True)

def verificar_resposta_seguranca(email: str, resposta: str) -> bool:
    u = buscar_usuario_email(email)
    if not u or not u.get('security_answer_hash'):
        return False
    return check_password_hash(u['security_answer_hash'], resposta.lower().strip())

def buscar_usuario_email(email: str) -> dict | None:
    ph = _PH
    return _exec(
        f'SELECT * FROM usuarios WHERE email={ph}',
        (email.lower().strip(),), fetch='one'
    )

def buscar_usuario_id(user_id: int) -> dict | None:
    ph = _PH
    return _exec(
        f'SELECT * FROM usuarios WHERE id={ph}',
        (user_id,), fetch='one'
    )


# ── Reset de senha por token ────────────────────────────────────────────────

def _ensure_reset_tokens_table():
    _exec(f'''
        CREATE TABLE IF NOT EXISTS reset_tokens (
            token      TEXT PRIMARY KEY,
            email      TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used       INTEGER DEFAULT 0
        )
    ''', commit=True)


def criar_token_reset(email: str) -> str:
    """Gera um token seguro de 1h para reset de senha e salva no banco.

    Invalida tokens anteriores do mesmo e-mail antes de criar o novo.
    """
    import secrets
    _ensure_reset_tokens_table()
    ph = _PH
    token = secrets.token_urlsafe(32)
    # Expirar tokens antigos do mesmo e-mail
    _exec(f'UPDATE reset_tokens SET used=1 WHERE email={ph}', (email.lower(),), commit=True)
    if _USE_PG:
        _exec(
            f"INSERT INTO reset_tokens (token, email, expires_at) VALUES ({ph},{ph}, NOW() + INTERVAL '1 hour')",
            (token, email.lower()), commit=True,
        )
    else:
        _exec(
            f"INSERT INTO reset_tokens (token, email, expires_at) VALUES ({ph},{ph}, datetime('now','+1 hour'))",
            (token, email.lower()), commit=True,
        )
    return token


def validar_token_reset(token: str) -> str | None:
    """Retorna o e-mail se o token for válido e não expirado, caso contrário None."""
    _ensure_reset_tokens_table()
    ph = _PH
    if _USE_PG:
        row = _exec(
            f'SELECT email FROM reset_tokens WHERE token={ph} AND used=0 AND expires_at > NOW()',
            (token,), fetch='one',
        )
    else:
        row = _exec(
            f"SELECT email FROM reset_tokens WHERE token={ph} AND used=0 AND expires_at > datetime('now')",
            (token,), fetch='one',
        )
    return row['email'] if row else None


def consumir_token_reset(token: str):
    """Marca o token como usado após a senha ser redefinida."""
    ph = _PH
    _exec(f'UPDATE reset_tokens SET used=1 WHERE token={ph}', (token,), commit=True)

def atualizar_perfil_consultoria(user_id: int, nome_consultoria: str, logo_base64: str):
    ph = _PH
    _exec(f'UPDATE usuarios SET nome_consultoria={ph}, logo_base64={ph} WHERE id={ph}',
          ((nome_consultoria or '').strip()[:120], logo_base64 or '', user_id), commit=True)

def verificar_senha(email: str, senha: str) -> dict | None:
    u = buscar_usuario_email(email)
    if not u or not u.get('senha_hash'):
        return None
    try:
        if check_password_hash(u['senha_hash'], senha):
            return u
    except Exception:
        pass
    return None

def listar_usuarios() -> list:
    return _exec(
        'SELECT id, email, nome, created_at FROM usuarios ORDER BY id',
        fetch='all'
    ) or []

def remover_usuario(user_id: int):
    ph = _PH
    _exec(f'DELETE FROM empresa_membros WHERE user_id={ph}', (user_id,), commit=True)
    _exec(f'DELETE FROM usuarios WHERE id={ph}', (user_id,), commit=True)

# ─────────────────────────────────────────────
# FAZENDAS
# ─────────────────────────────────────────────
def criar_fazenda(nome: str, proprietario: str = '', municipio: str = '',
                  estado: str = '', empresa_id: int = None, criado_por: int = None) -> int:
    ph = _PH
    rid = _exec(
        f'''INSERT INTO fazendas (user_id, empresa_id, nome, proprietario, municipio, estado)
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph})''',
        (criado_por, empresa_id, nome.strip()[:120], proprietario.strip()[:120],
         municipio.strip()[:80], estado.strip()[:40]),
        fetch='lastrow', commit=True
    )
    return int(rid)

def listar_fazendas(empresa_id: int) -> list:
    ph = _PH
    rows = _exec(
        f'''SELECT f.id, f.nome, f.proprietario, f.municipio, f.estado,
                   f.created_at,
                   COUNT(r.id) as total_analises,
                   MAX(r.created_at) as ultima_analise
            FROM fazendas f
            LEFT JOIN registros r ON r.fazenda_id = f.id
            WHERE f.empresa_id = {ph}
            GROUP BY f.id, f.nome, f.proprietario, f.municipio, f.estado, f.created_at
            ORDER BY ultima_analise DESC NULLS LAST, f.created_at DESC''',
        (empresa_id,), fetch='all'
    ) or []
    result = []
    for r in rows:
        d = dict(r)
        d['created_at'] = str(d.get('created_at', ''))
        d['ultima_analise'] = str(d.get('ultima_analise', '') or '')
        result.append(d)
    return result

def buscar_fazenda(fazenda_id: int, empresa_id: int = None) -> dict | None:
    ph = _PH
    sql = f'SELECT * FROM fazendas WHERE id={ph}'
    params = [fazenda_id]
    if empresa_id is not None:
        sql += f' AND empresa_id={ph}'
        params.append(empresa_id)
    return _exec(sql, tuple(params), fetch='one')

def historico_fazenda(fazenda_id: int, limit: int = 30) -> list:
    ph = _PH
    rows = _exec(
        f'''SELECT r.id, r.valores, r.class_ml, r.class_conf, r.confianca,
                   r.nat_pct, r.created_at
            FROM registros r
            WHERE r.fazenda_id={ph}
            ORDER BY r.created_at DESC LIMIT {ph}''',
        (fazenda_id, limit), fetch='all'
    ) or []
    result = []
    for r in rows:
        d = dict(r)
        d['valores'] = json.loads(d['valores'])
        d['created_at'] = str(d.get('created_at', ''))
        result.append(d)
    return result

def salvar_parecer(user_id: int, fazenda_id: int,
                   solicitacao: dict, parecer: dict) -> int:
    ph = _PH
    concl = (parecer or {}).get('conclusao', {})
    rid = _exec(
        f'''INSERT INTO pareceres (fazenda_id, user_id, solicitacao, parecer,
                                   recomendacao, dscr)
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph})''',
        (fazenda_id, user_id, json.dumps(solicitacao), json.dumps(parecer),
         concl.get('recomendacao'), concl.get('dscr')),
        fetch='lastrow', commit=True
    )
    return int(rid)

def listar_pareceres(fazenda_id: int, limit: int = 30) -> list:
    ph = _PH
    rows = _exec(
        f'''SELECT id, solicitacao, parecer, recomendacao, dscr, created_at
            FROM pareceres WHERE fazenda_id={ph}
            ORDER BY created_at DESC, id DESC LIMIT {ph}''',
        (fazenda_id, limit), fetch='all'
    ) or []
    for r in rows:
        r['created_at'] = str(r.get('created_at', ''))
    return rows

def excluir_registro(registro_id: int, user_id: int) -> bool:
    ph = _PH
    _exec(f'DELETE FROM registros WHERE id={ph} AND user_id={ph}',
          (registro_id, user_id), commit=True)
    return True

def excluir_fazenda(fazenda_id: int, empresa_id: int) -> bool:
    ph = _PH
    if not buscar_fazenda(fazenda_id, empresa_id):
        return False
    _exec(f'DELETE FROM registros WHERE fazenda_id={ph}', (fazenda_id,), commit=True)
    _exec(f'DELETE FROM pareceres WHERE fazenda_id={ph}', (fazenda_id,), commit=True)
    _exec(f'DELETE FROM fazendas WHERE id={ph} AND empresa_id={ph}',
          (fazenda_id, empresa_id), commit=True)
    return True


# ─────────────────────────────────────────────
# CLASSIFICAÇÕES
# ─────────────────────────────────────────────
def salvar(valores: list, class_ml: str, confianca: float,
           fazenda: str = '', municipio: str = '', nat_pct: float = 75.0,
           user_id: int = None, fazenda_id: int = None) -> int:
    ph = _PH
    sql = f'''INSERT INTO registros
               (valores, class_ml, confianca, fazenda, municipio, nat_pct, user_id, fazenda_id)
               VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})'''
    params = (json.dumps(valores), class_ml, round(confianca, 2),
              fazenda[:120], municipio[:120], nat_pct, user_id, fazenda_id)
    rid = _exec(sql, params, fetch='lastrow', commit=True)
    return int(rid)

def confirmar(registro_id: int, class_conf: str):
    VALIDOS = {'CRIA', 'RECRIA', 'ENGORDA', 'CICLO_COMPLETO',
               'RECRIA_ENGORDA', 'CRIA_RECRIA'}
    if class_conf not in VALIDOS:
        raise ValueError(f'Classificacao invalida: {class_conf}')
    ph = _PH
    _exec(f'UPDATE registros SET class_conf={ph} WHERE id={ph}',
          (class_conf, registro_id), commit=True)

def exportar_treino():
    TIPOS = ['CRIA', 'RECRIA', 'ENGORDA', 'CICLO_COMPLETO',
             'RECRIA_ENGORDA', 'CRIA_RECRIA']
    rows = _exec(
        'SELECT valores, class_conf FROM registros WHERE class_conf IS NOT NULL',
        fetch='all'
    ) or []
    X, y = [], []
    for r in rows:
        t = r['class_conf']
        if t in TIPOS:
            X.append(json.loads(r['valores']))
            y.append(TIPOS.index(t))
    return X, y

def buscar_registro_por_id(registro_id: int) -> dict | None:
    ph = _PH
    row = _exec(f'SELECT id, fazenda, valores, class_ml FROM registros WHERE id={ph}',
                (registro_id,), fetch='one')
    return dict(row) if row else None


def listar_registros_por_fazendas(nomes_fazendas: list, limit: int = 60) -> list:
    """Lista registros cujo campo fazenda está na lista fornecida."""
    if not nomes_fazendas:
        return []
    ph = _PH
    placeholders = ','.join([ph] * len(nomes_fazendas))
    rows = _exec(
        f'''SELECT id, valores, class_ml, class_conf, confianca,
                   fazenda, municipio, created_at, nat_pct
            FROM registros
            WHERE fazenda IN ({placeholders})
            ORDER BY created_at DESC LIMIT {ph}''',
        tuple(nomes_fazendas) + (limit,), fetch='all'
    ) or []
    result = []
    for r in rows:
        d = dict(r)
        try:
            d['valores'] = json.loads(d['valores']) if isinstance(d['valores'], str) else d['valores']
        except Exception:
            pass
        d['created_at'] = str(d.get('created_at', ''))
        result.append(d)
    return result


def listar(limit: int = 60, user_id: int = None) -> list:
    ph = _PH
    sql = 'SELECT id, valores, class_ml, class_conf, confianca, fazenda, municipio, created_at FROM registros'
    params = []
    if user_id is not None:
        sql += f' WHERE user_id={ph}'
        params.append(user_id)

    sql += f' ORDER BY created_at DESC LIMIT {ph}'
    params.append(limit)

    rows = _exec(sql, tuple(params), fetch='all') or []
    result = []
    for r in rows:
        d = dict(r)
        try:
            d['valores'] = json.loads(d['valores']) if isinstance(d['valores'], str) else (d['valores'] or [])
        except Exception:
            d['valores'] = []
        d['created_at'] = str(d.get('created_at', ''))
        result.append(d)
    return result

def stats(user_id: int = None) -> dict:
    ph = _PH
    if user_id is not None:
        sql_tot  = f'SELECT COUNT(*) as n FROM registros WHERE user_id={ph}'
        sql_conf = f'SELECT COUNT(*) as n FROM registros WHERE class_conf IS NOT NULL AND user_id={ph}'
        sql_tipo = f'SELECT class_conf, COUNT(*) as n FROM registros WHERE class_conf IS NOT NULL AND user_id={ph} GROUP BY class_conf'
        params = (user_id,)
    else:
        sql_tot  = 'SELECT COUNT(*) as n FROM registros'
        sql_conf = 'SELECT COUNT(*) as n FROM registros WHERE class_conf IS NOT NULL'
        sql_tipo = 'SELECT class_conf, COUNT(*) as n FROM registros WHERE class_conf IS NOT NULL GROUP BY class_conf'
        params = ()

    total = (_exec(sql_tot,  params, fetch='one') or {}).get('n', 0)
    conf  = (_exec(sql_conf, params, fetch='one') or {}).get('n', 0)
    rows  = _exec(sql_tipo,  params, fetch='all') or []

    return {
        'total':       int(total),
        'confirmados': int(conf),
        'por_tipo':    {r['class_conf']: r['n'] for r in rows},
    }

# ─────────────────────────────────────────────
# COTAÇÕES DA ARROBA (FINANÇAS)
# ─────────────────────────────────────────────
def guardar_cotacao_diaria(precos: dict):
    """
    Insere ou atualiza o preço da arroba para a data atual.
    Compatível com PostgreSQL e SQLite através da função abstrata _exec.
    """
    hoje = datetime.now().strftime('%Y-%m-%d')
    ph = _PH
    boi = float(precos.get('boi', 0.0))
    vaca = float(precos.get('vaca', 0.0))
    china = float(precos.get('boi_china', 0.0))
    bezerro = float(precos.get('bezerro', 0.0))
    bezerra = float(precos.get('bezerra', 0.0))

    # Verifica se já existe um registro para o dia de hoje
    existente = _exec(f'SELECT id FROM cotacao_arroba WHERE data_cotacao={ph}', (hoje,), fetch='one')

    if existente:
        # Se existir, atualiza (Evita erros de constraint UNIQUE na data)
        _exec(f'''UPDATE cotacao_arroba
                  SET preco_boi={ph}, preco_vaca={ph}, preco_boi_china={ph},
                      preco_bezerro={ph}, preco_bezerra={ph}
                  WHERE id={ph}''',
              (boi, vaca, china, bezerro, bezerra, existente['id']), commit=True)
    else:
        # Se não existir, insere um novo registro histórico
        _exec(f'''INSERT INTO cotacao_arroba (data_cotacao, preco_boi, preco_vaca,
                      preco_boi_china, preco_bezerro, preco_bezerra)
                  VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})''',
              (hoje, boi, vaca, china, bezerro, bezerra), commit=True)

def obter_cotacoes_atuais() -> dict:
    """
    Busca o preço mais recente no banco de dados.
    Retorna dicionário {'boi': valor, 'vaca': valor, 'boi_china': valor}
    """
    try:
        resultado = _exec('SELECT preco_boi, preco_vaca, preco_boi_china, preco_bezerro, preco_bezerra FROM cotacao_arroba ORDER BY data_cotacao DESC LIMIT 1', fetch='one')
        if resultado:
            return {
                'boi': float(resultado['preco_boi'] or 0.0),
                'vaca': float(resultado['preco_vaca'] or 0.0),
                'boi_china': float(resultado.get('preco_boi_china') or 0.0),
                'bezerro': float(resultado.get('preco_bezerro') or 0.0),
                'bezerra': float(resultado.get('preco_bezerra') or 0.0),
            }
    except Exception as e:
        print(f"[Erro DB Cotação]: {e}")
        
    # Preços de segurança (fallback) caso o banco esteja vazio
    return {'boi': 0.0, 'vaca': 0.0, 'boi_china': 0.0}


# ─────────────────────────────────────────────
# META (KV genérica — multi-worker safe)
# ─────────────────────────────────────────────
def get_meta(chave: str, default: str = '0') -> str:
    ph = _PH
    row = _exec(f'SELECT valor FROM meta WHERE chave={ph}', (chave,), fetch='one')
    if row is None:
        return default
    return str(row['valor'])


def set_meta(chave: str, valor) -> None:
    ph = _PH
    valor_str = str(valor)
    if _USE_PG:
        _exec(
            f'''INSERT INTO meta (chave, valor) VALUES ({ph},{ph})
                ON CONFLICT (chave) DO UPDATE SET valor=EXCLUDED.valor''',
            (chave, valor_str), commit=True
        )
    else:
        _exec(
            f'INSERT OR REPLACE INTO meta (chave, valor) VALUES ({ph},{ph})',
            (chave, valor_str), commit=True
        )


def incr_meta(chave: str, delta: int = 1) -> int:
    """Incrementa atomicamente um contador inteiro e retorna o novo valor.

    Em PostgreSQL usa UPDATE atômico. Em SQLite (single-writer) usa
    transação simples — suficiente porque SQLite serializa writes.
    """
    ph = _PH
    if _USE_PG:
        # UPSERT atômico via INSERT ... ON CONFLICT
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f'''INSERT INTO meta (chave, valor) VALUES ({ph},{ph})
                        ON CONFLICT (chave) DO UPDATE
                        SET valor = (CAST(meta.valor AS BIGINT) + {ph})::TEXT
                        RETURNING valor''',
                    (chave, str(delta), delta)
                )
                novo = cur.fetchone()[0]
                conn.commit()
                return int(novo)
    else:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(f'SELECT valor FROM meta WHERE chave={ph}', (chave,))
            row = cur.fetchone()
            atual = int(row['valor']) if row else 0
            novo = atual + delta
            cur.execute(
                f'INSERT OR REPLACE INTO meta (chave, valor) VALUES ({ph},{ph})',
                (chave, str(novo))
            )
            conn.commit()
            return novo


def reset_meta(chave: str) -> None:
    set_meta(chave, '0')