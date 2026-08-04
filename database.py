"""
Fluxo de Gestão — Camada de persistência
Usa PostgreSQL (via DATABASE_URL) em produção e SQLite localmente.
"""
import json, os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
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
    _BIN = 'BYTEA'

    def _blob(b):
        """psycopg2 não adapta `bytes` sozinho — precisa do wrapper Binary."""
        return psycopg2.Binary(b or b'')
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
    _BIN = 'BLOB'

    def _blob(b):
        """sqlite3 aceita `bytes` direto; sqlite3.Binary é o mesmo objeto."""
        return sqlite3.Binary(b or b'')
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
    hoje = datetime.now(ZoneInfo(os.environ.get('APP_TIMEZONE',
                                                'America/Porto_Velho'))).strftime('%Y-%m-%d')
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
        hoje = datetime.now(ZoneInfo(os.environ.get('APP_TIMEZONE',
                                                    'America/Porto_Velho'))).strftime('%Y-%m-%d')
        resultado = _exec(
            f'''SELECT preco_boi, preco_vaca, preco_boi_china,
                       preco_bezerro, preco_bezerra
                FROM cotacao_arroba
                WHERE data_cotacao<={_PH}
                ORDER BY data_cotacao DESC LIMIT 1''',
            (hoje,), fetch='one')
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

def contar_confirmados() -> int:
    """
    Quantos registros têm classificação confirmada por um humano.

    É a métrica que separa "o modelo aprendeu as faixas que escrevemos" de
    "o modelo acerta na realidade": todo o conjunto de treino é sintético, e
    só estes registros são casos reais rotulados.
    """
    row = _exec('SELECT COUNT(*) AS n FROM registros WHERE class_conf IS NOT NULL',
                fetch='one')
    if not row:
        return 0
    try:
        return int(row['n'])
    except (TypeError, KeyError, IndexError):
        return int(tuple(row)[0])


# ═══════════════════════════════════════════════════════════════════════════
# WHATSAPP — vínculo telefone → usuário
# ═══════════════════════════════════════════════════════════════════════════
# O webhook recebe um número de telefone e nada mais. Sem um vínculo explícito,
# responder qualquer pergunta sobre um parecer seria entregar dado de crédito
# de um cliente a quem souber o número do bot. O vínculo é criado pelo próprio
# analista, logado no sistema, com um código de uso único e prazo curto.

def _ensure_whatsapp_tables():
    _exec(f'''
        CREATE TABLE IF NOT EXISTS whatsapp_vinculos (
            telefone   TEXT PRIMARY KEY,
            user_id    INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT {_NOW}
        )
    ''', commit=True)
    _exec(f'''
        CREATE TABLE IF NOT EXISTS whatsapp_codigos (
            codigo     TEXT PRIMARY KEY,
            user_id    INTEGER NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used       INTEGER DEFAULT 0
        )
    ''', commit=True)


def criar_codigo_whatsapp(user_id: int, ttl_min: int = 15) -> str:
    """Código curto de uso único para o analista vincular o próprio número."""
    import random
    _ensure_whatsapp_tables()
    codigo = f'{random.randint(0, 999999):06d}'
    expira = datetime.now() + timedelta(minutes=ttl_min)
    ph = _PH
    _exec(f'DELETE FROM whatsapp_codigos WHERE user_id={ph}', (user_id,), commit=True)
    _exec(f'INSERT INTO whatsapp_codigos (codigo, user_id, expires_at) VALUES ({ph},{ph},{ph})',
          (codigo, user_id, expira), commit=True)
    return codigo


def consumir_codigo_whatsapp(codigo: str, telefone: str):
    """
    Troca um código válido pelo vínculo. Devolve o user_id ou None.

    Uso único e com prazo: um código vazado depois de usado não serve, e um
    código esquecido numa conversa expira sozinho.
    """
    _ensure_whatsapp_tables()
    ph = _PH
    row = _exec(f'SELECT user_id, expires_at, used FROM whatsapp_codigos WHERE codigo={ph}',
                ((codigo or '').strip(),), fetch='one')
    if not row or row['used']:
        return None
    exp = row['expires_at']
    if isinstance(exp, str):
        exp = datetime.fromisoformat(exp)
    if exp < datetime.now():
        return None
    uid = int(row['user_id'])
    _exec(f'UPDATE whatsapp_codigos SET used=1 WHERE codigo={ph}', (codigo,), commit=True)
    _exec(f'DELETE FROM whatsapp_vinculos WHERE telefone={ph}', (telefone,), commit=True)
    _exec(f'INSERT INTO whatsapp_vinculos (telefone, user_id) VALUES ({ph},{ph})',
          (telefone, uid), commit=True)
    return uid


def buscar_user_por_telefone(telefones: list):
    """Resolve um telefone (em suas variantes) para o usuário vinculado."""
    _ensure_whatsapp_tables()
    if not telefones:
        return None
    ph = _PH
    marcadores = ','.join([ph] * len(telefones))
    row = _exec(f'SELECT user_id FROM whatsapp_vinculos WHERE telefone IN ({marcadores})',
                tuple(telefones), fetch='one')
    return int(row['user_id']) if row else None


def ultimo_parecer_do_usuario(user_id: int):
    """O parecer mais recente do analista — o contexto que o chat responde."""
    ph = _PH
    row = _exec(
        f'''SELECT id, solicitacao, parecer, recomendacao, dscr, created_at
            FROM pareceres WHERE user_id={ph}
            ORDER BY created_at DESC, id DESC LIMIT 1''',
        (user_id,), fetch='one')
    if not row:
        return None
    out = dict(row)
    for k in ('solicitacao', 'parecer'):
        if isinstance(out.get(k), str):
            try:
                out[k] = json.loads(out[k])
            except (ValueError, TypeError):
                out[k] = {}
    out['created_at'] = str(out.get('created_at', ''))
    return out


# ═══════════════════════════════════════════════════════════════════════════
# AUDITORIA DE ACESSO — quem viu o quê, quando, de onde
# ═══════════════════════════════════════════════════════════════════════════
# Append-only por desenho: não existe update nem delete aqui. Uma trilha que
# pode ser editada não é trilha. Ver services/auditoria.py.

def _ensure_auditoria_table():
    _exec(f'''
        CREATE TABLE IF NOT EXISTS auditoria_acessos (
            id         {_AI},
            user_id    INTEGER,
            user_email TEXT,
            evento     TEXT NOT NULL,
            recurso    TEXT,
            recurso_id TEXT,
            detalhe    TEXT,
            ip         TEXT,
            sucesso    INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT {_NOW}
        )
    ''', commit=True)
    for sql in (
        'CREATE INDEX IF NOT EXISTS ix_aud_user ON auditoria_acessos (user_id)',
        'CREATE INDEX IF NOT EXISTS ix_aud_evento ON auditoria_acessos (evento)',
        'CREATE INDEX IF NOT EXISTS ix_aud_data ON auditoria_acessos (created_at)',
    ):
        try:
            _exec(sql, commit=True)
        except Exception:
            pass


def registrar_acesso(evento: str, *, user_id=None, user_email=None,
                     recurso=None, recurso_id=None, detalhe=None,
                     ip=None, sucesso=True) -> None:
    """
    Grava um evento na trilha. NUNCA levanta.

    Um parecer não pode falhar porque a auditoria caiu — e um sistema que falha
    assim acaba com a auditoria desligada na primeira sexta-feira ruim.
    """
    try:
        _ensure_auditoria_table()
        ph = _PH
        _exec(
            f'''INSERT INTO auditoria_acessos
                (user_id, user_email, evento, recurso, recurso_id, detalhe, ip, sucesso)
                VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})''',
            (user_id, (user_email or '')[:200], evento, recurso,
             None if recurso_id is None else str(recurso_id)[:64],
             (detalhe or '')[:500] or None, ip, 1 if sucesso else 0),
            commit=True)
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            'falha ao registrar auditoria (evento=%s) — operação segue',
            evento, exc_info=True)


def listar_acessos(*, limit: int = 200, user_id=None, evento=None,
                   desde=None) -> list:
    """Consulta da trilha, do mais recente para o mais antigo."""
    _ensure_auditoria_table()
    ph = _PH
    onde, params = [], []
    if user_id is not None:
        onde.append(f'user_id={ph}'); params.append(int(user_id))
    if evento:
        onde.append(f'evento={ph}'); params.append(evento)
    if desde:
        onde.append(f'created_at>={ph}'); params.append(desde)
    sql = 'SELECT * FROM auditoria_acessos'
    if onde:
        sql += ' WHERE ' + ' AND '.join(onde)
    sql += f' ORDER BY created_at DESC, id DESC LIMIT {ph}'
    params.append(int(limit))
    rows = _exec(sql, tuple(params), fetch='all') or []
    for r in rows:
        r['created_at'] = str(r.get('created_at', ''))
        r['sucesso'] = bool(r.get('sucesso', 1))
    return rows


def contar_acessos() -> int:
    _ensure_auditoria_table()
    row = _exec('SELECT COUNT(*) AS n FROM auditoria_acessos', fetch='one')
    if not row:
        return 0
    try:
        return int(row['n'])
    except (TypeError, KeyError, IndexError):
        return int(tuple(row)[0])


# ═══════════════════════════════════════════════════════════════════════════
# LGPD — anonimização, portabilidade e retenção
# ═══════════════════════════════════════════════════════════════════════════
# Ver services/lgpd.py para o porquê de anonimizar em vez de excluir.

def anonimizar_usuario(user_id: int) -> dict:
    """
    Atende o direito de eliminação (Art. 18) sem quebrar a trilha de auditoria.

    Os campos que identificam a pessoa viram pseudônimo estável; o registro dos
    eventos permanece. A conta fica inutilizável — a senha vira um hash de
    valor aleatório que ninguém conhece.

    O PARECER NÃO É APAGADO. Ele é dado do cliente da consultoria, tem valor
    probatório para a instituição e prazo próprio de guarda; o vínculo com o
    analista é que deixa de identificar uma pessoa.

    Idempotente: rodar duas vezes não muda nada na segunda.
    """
    import secrets
    from services.lgpd import pseudonimo, e_anonimo

    ph = _PH
    u = buscar_usuario_id(user_id)
    if not u:
        return {'ok': False, 'erro': 'usuário não encontrado'}
    if e_anonimo(u.get('email')):
        return {'ok': True, 'ja_anonimo': True, 'user_id': user_id,
                'tabelas': {}}

    pseudo = pseudonimo(u['email'])
    tocadas = {}

    _exec(f'''UPDATE usuarios SET email={ph}, nome={ph}, senha_hash={ph},
                     nome_consultoria={ph}, security_question=NULL,
                     security_answer_hash=NULL
              WHERE id={ph}''',
          (pseudo + '@anonimizado.local', pseudo,
           generate_password_hash(secrets.token_urlsafe(32)), '', user_id),
          commit=True)
    tocadas['usuarios'] = 1

    _ensure_auditoria_table()
    _exec(f'UPDATE auditoria_acessos SET user_email={ph}, ip=NULL WHERE user_id={ph}',
          (pseudo, user_id), commit=True)
    tocadas['auditoria_acessos'] = 'pseudonimizado'

    _ensure_whatsapp_tables()
    _exec(f'DELETE FROM whatsapp_vinculos WHERE user_id={ph}', (user_id,), commit=True)
    _exec(f'DELETE FROM whatsapp_codigos WHERE user_id={ph}', (user_id,), commit=True)
    tocadas['whatsapp'] = 'removido'

    try:
        _exec(f'DELETE FROM reset_tokens WHERE email={ph}', (u['email'],), commit=True)
        tocadas['reset_tokens'] = 'removido'
    except Exception:
        pass

    registrar_acesso('lgpd_anonimizacao', user_id=user_id, user_email=pseudo,
                     recurso='usuario', recurso_id=user_id,
                     detalhe='direito de eliminação (Art. 18)')
    return {'ok': True, 'ja_anonimo': False, 'user_id': user_id,
            'pseudonimo': pseudo, 'tabelas': tocadas}


def exportar_dados_usuario(user_id: int) -> dict:
    """
    Portabilidade (Art. 18, V): tudo que o sistema guarda sobre um usuário.

    Inclui a trilha de acesso dele — é dado sobre ele, e omitir seria entregar
    uma portabilidade parcial.
    """
    u = buscar_usuario_id(user_id)
    if not u:
        return {}
    ph = _PH
    conta = {k: v for k, v in u.items()
             if k not in ('senha_hash', 'security_answer_hash', 'logo_base64')}
    return {
        'conta':     conta,
        'empresas':  _exec(f'''SELECT e.id, e.nome FROM empresas e
                               JOIN empresa_membros m ON m.empresa_id=e.id
                               WHERE m.user_id={ph}''', (user_id,), fetch='all') or [],
        'fazendas':  _exec(f'SELECT * FROM fazendas WHERE user_id={ph}',
                           (user_id,), fetch='all') or [],
        'auditoria': listar_acessos(user_id=user_id, limit=5000),
        'aviso': ('Pareceres e registros de rebanho são dados dos clientes da '
                  'consultoria, não do usuário, e não entram nesta exportação.'),
    }


def purgar_auditoria(dias: int = None) -> int:
    """
    Retenção da trilha: descarta eventos mais antigos que `dias`.

    Guardar e-mail e IP indefinidamente é acúmulo sem finalidade — e a
    finalidade declarada (investigação de incidente) tem prazo. Devolve quantos
    registros foram removidos.
    """
    from services.lgpd import RETENCAO_AUDITORIA_DIAS
    dias = RETENCAO_AUDITORIA_DIAS if dias is None else int(dias)
    if dias <= 0:
        return 0
    _ensure_auditoria_table()
    corte = datetime.now() - timedelta(days=dias)
    ph = _PH
    antes = contar_acessos()
    _exec(f'DELETE FROM auditoria_acessos WHERE created_at < {ph}',
          (corte,), commit=True)
    removidos = antes - contar_acessos()
    if removidos:
        registrar_acesso('lgpd_purga_auditoria',
                         detalhe=f'{removidos} registro(s) além de {dias} dias')
    return removidos


# ═══════════════════════════════════════════════════════════════════════════
# 2FA (TOTP)
# ═══════════════════════════════════════════════════════════════════════════

def _ensure_totp_colunas():
    for col, tipo in (('totp_segredo', 'TEXT'), ('totp_ativo', 'INTEGER DEFAULT 0'),
                      ('totp_contador', 'INTEGER DEFAULT 0'),
                      ('totp_backup', 'TEXT')):
        _add_column_safe('usuarios', col, tipo)


def totp_estado(user_id: int) -> dict:
    _ensure_totp_colunas()
    ph = _PH
    row = _exec(
        f'SELECT totp_segredo, totp_ativo, totp_contador, totp_backup '
        f'FROM usuarios WHERE id={ph}', (user_id,), fetch='one')
    if not row:
        return {'ativo': False, 'segredo': None, 'contador': 0, 'backup': []}
    return {
        'ativo':    bool(row.get('totp_ativo')),
        'segredo':  row.get('totp_segredo'),
        'contador': int(row.get('totp_contador') or 0),
        'backup':   json.loads(row.get('totp_backup') or '[]'),
    }


def totp_guardar_segredo(user_id: int, segredo: str) -> None:
    """Grava o segredo AINDA INATIVO — só ativa depois de um código válido."""
    _ensure_totp_colunas()
    ph = _PH
    _exec(f'UPDATE usuarios SET totp_segredo={ph}, totp_ativo=0 WHERE id={ph}',
          (segredo, user_id), commit=True)


def totp_ativar(user_id: int, hashes_backup: list) -> None:
    _ensure_totp_colunas()
    ph = _PH
    _exec(f'UPDATE usuarios SET totp_ativo=1, totp_backup={ph} WHERE id={ph}',
          (json.dumps(hashes_backup), user_id), commit=True)


def totp_desativar(user_id: int) -> None:
    _ensure_totp_colunas()
    ph = _PH
    _exec(f'UPDATE usuarios SET totp_ativo=0, totp_segredo=NULL, '
          f'totp_backup=NULL, totp_contador=0 WHERE id={ph}',
          (user_id,), commit=True)


def totp_registrar_uso(user_id: int, contador: int) -> None:
    """
    Registra o contador aceito para impedir reuso do MESMO código dentro da
    janela de 90s. Sem isto, código interceptado vale de novo.
    """
    _ensure_totp_colunas()
    ph = _PH
    _exec(f'UPDATE usuarios SET totp_contador={ph} WHERE id={ph}',
          (int(contador), user_id), commit=True)


def totp_consumir_backup(user_id: int, hash_usado: str) -> None:
    """Uso único: o hash sai da lista assim que é aceito."""
    est = totp_estado(user_id)
    restantes = [h for h in est['backup'] if h != hash_usado]
    ph = _PH
    _exec(f'UPDATE usuarios SET totp_backup={ph} WHERE id={ph}',
          (json.dumps(restantes), user_id), commit=True)


# ── Acervo de documentos lidos ───────────────────────────────────────────────
# O PDF enviado era lido e apagado (`os.unlink` no finally de /api/ler-pdf).
# Cada ficha real que passou pelo sistema achou um defeito que os testes
# sintéticos não achavam — ver o cabeçalho de services/documentos.py. Guardar
# o documento, o que o parser leu e o que o analista corrigiu é o que
# transforma uso em cobertura de teste e em calibração.

def _ensure_documentos_table():
    _exec(f'''
        CREATE TABLE IF NOT EXISTS documentos (
            id           {_AI},
            empresa_id   INTEGER,
            user_id      INTEGER,
            fazenda_id   INTEGER,
            nome_arquivo TEXT,
            sha256       TEXT NOT NULL,
            tamanho      INTEGER DEFAULT 0,
            conteudo     {_BIN},
            origem       TEXT,
            parse        TEXT,
            valores_lidos TEXT,
            valores_usados TEXT,
            situacao     TEXT,
            divergencia  TEXT,
            revisado     INTEGER DEFAULT 0,
            created_at   TIMESTAMP DEFAULT {_NOW}
        )
    ''', commit=True)
    for sql in (
        'CREATE INDEX IF NOT EXISTS ix_doc_sha ON documentos (sha256)',
        'CREATE INDEX IF NOT EXISTS ix_doc_empresa ON documentos (empresa_id)',
        'CREATE INDEX IF NOT EXISTS ix_doc_situacao ON documentos (situacao)',
    ):
        try:
            _exec(sql, commit=True)
        except Exception:
            pass


def registrar_documento(*, empresa_id, user_id, nome_arquivo, conteudo: bytes,
                        sha256: str, origem: str, parse: dict,
                        valores_lidos: list) -> int:
    """Guarda o documento e o que o parser extraiu dele.

    Deduplica por sha256 DENTRO da empresa: o mesmo produtor reenvia a mesma
    ficha várias vezes numa análise, e N cópias idênticas só encarecem o banco.
    Entre empresas não deduplica — o isolamento entre consultorias vale mais
    que o byte economizado, e uma delas pode apagar o dado da outra.
    """
    _ensure_documentos_table()
    ph = _PH
    ja = _exec(
        f'SELECT id FROM documentos WHERE sha256={ph} AND empresa_id={ph}',
        (sha256, empresa_id), fetch='one')
    if ja:
        return int(ja['id'])

    # O parse pode carregar chaves não serializáveis vindas dos parsers.
    try:
        parse_json = json.dumps(parse, ensure_ascii=False, default=str)
    except Exception:
        parse_json = '{}'

    did = _exec(
        f'''INSERT INTO documentos
              (empresa_id, user_id, nome_arquivo, sha256, tamanho, conteudo,
               origem, parse, valores_lidos)
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})''',
        (empresa_id, user_id, (nome_arquivo or '')[:255], sha256,
         len(conteudo or b''), _blob(conteudo), origem, parse_json,
         json.dumps(valores_lidos)),
        fetch='lastrow', commit=True)
    return int(did)


def registrar_correcao(documento_id: int, valores_usados: list,
                       comparacao: dict, fazenda_id=None) -> None:
    """Fecha o par: o que o parser leu × o que o analista de fato usou.

    É esta metade que ensina. Um documento sem a correção é depósito; com ela,
    vira rótulo humano apontando em qual faixa o parser tropeça.
    """
    _ensure_documentos_table()
    ph = _PH
    _exec(
        f'''UPDATE documentos
               SET valores_usados={ph}, situacao={ph}, divergencia={ph},
                   fazenda_id=COALESCE({ph}, fazenda_id)
             WHERE id={ph}''',
        (json.dumps(valores_usados),
         comparacao.get('situacao'),
         json.dumps(comparacao, ensure_ascii=False),
         fazenda_id, documento_id),
        commit=True)


def documentos_para_revisao(limite: int = 50) -> list:
    """Fila dos casos em que o parser errou — os que viram fixture.

    Um parse que conferiu não ensina nada; o que ensina é o erro.
    """
    _ensure_documentos_table()
    ph = _PH
    return _exec(
        f'''SELECT id, empresa_id, nome_arquivo, origem, situacao, divergencia,
                   tamanho, created_at
              FROM documentos
             WHERE situacao IN ('divergencia','parser_vazio') AND revisado=0
          ORDER BY created_at DESC
             LIMIT {ph}''',
        (limite,), fetch='all') or []


def documento_conteudo(documento_id: int, empresa_id: int):
    """Devolve o PDF guardado, restrito à empresa dona.

    O filtro por empresa é a fronteira de isolamento entre consultorias — sem
    ele o id sequencial deixaria qualquer analista baixar ficha de cliente de
    outra empresa.
    """
    _ensure_documentos_table()
    ph = _PH
    row = _exec(
        f'SELECT nome_arquivo, conteudo FROM documentos WHERE id={ph} AND empresa_id={ph}',
        (documento_id, empresa_id), fetch='one')
    if not row:
        return None
    return row['nome_arquivo'], bytes(row['conteudo'] or b'')


def documento_parse(documento_id: int, empresa_id) -> list | None:
    """Vetor que o parser extraiu do documento, restrito à empresa dona."""
    if empresa_id is None:
        return None
    _ensure_documentos_table()
    ph = _PH
    row = _exec(
        f'SELECT valores_lidos FROM documentos WHERE id={ph} AND empresa_id={ph}',
        (documento_id, empresa_id), fetch='one')
    if not row or not row.get('valores_lidos'):
        return None
    try:
        return json.loads(row['valores_lidos'])
    except (ValueError, TypeError):
        return None
