"""PreToolUse (Bash): bloqueia comandos destrutivos claros (exit 2).

Só dispara quando o comando *executa* a ação. Texto dentro de aspas, mensagem
de commit, comentário, heredoc ou argumento de grep/echo/pytest não conta.
Qualquer falha de leitura/parsing libera o comando (exit 0): o hook nunca
trava o ambiente.

Limites conhecidos (não cobertos de propósito): `find -delete`, SQL em
script Python via heredoc (`python3 - <<EOF`, falso positivo demais), `psql -f
arquivo.sql`, `DELETE FROM` sem WHERE, SQL ofuscado, `$DATABASE_URL` sem o
host explícito no comando e expansões que só existem em tempo de execução.
"""
import json
import os
import posixpath
import re
import shlex
import sys

INICIOS = {"{", "then", "do", "else", "elif", "if", "while", "until", "!", "time", "exec", "command", "nohup"}
LAUNCHERS = {"sudo", "doas", "env", "nice", "ionice", "timeout"}
FLAGS_COM_VALOR = {"-u", "-g", "-n", "-s", "-k", "-C", "-p"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "eval"}
WRAPPERS = {"ssh", "docker", "podman", "kubectl", "docker-compose", "xargs", "watch", "parallel"}
CLIENTES_DB = {"psql", "sqlite3", "mysql", "mariadb", "usql", "pgcli"}
SQL_DESTRUTIVO = re.compile(r"\b(drop\s+(table|database|schema|owned)|truncate(\s+table)?\s+[\w\"])", re.I)
ALVO_PRODUCAO = re.compile(r"supabase\.(co|com)|pooler\.supabase|credito\.orkavyn\.tech|/opt/orkavyn", re.I)
HEREDOC = re.compile(r"<<(-?)\s*(['\"]?)(\w+)\2")
VAR_PERIGOSA = re.compile(r"(\$\{?(HOME|PWD|OLDPWD|CLAUDE_PROJECT_DIR)\}?|\$\(pwd\)|`pwd`|~)(/\*?)?")
RELATIVOS_PERIGOSOS = {".", "*", ".*"}
MAX_PROFUNDIDADE = 3


# ── pré-processamento: comentários, heredocs, substituições ─────────────────

def _registrar_subst(cmd, i, subs):
    """Em `$(`, guarda o conteúdo para análise recursiva (sem avançar o índice)."""
    if cmd.startswith("$((", i) or not cmd.startswith("$(", i):
        return
    prof, j = 1, i + 2
    while j < len(cmd) and prof:
        prof += (cmd[j] == "(") - (cmd[j] == ")")
        j += 1
    subs.append(cmd[i + 2:j - 1 if prof == 0 else j])


def _preprocessar(cmd):
    """Devolve (comando_limpo, corpos_de_heredoc, substituições).

    Fora de aspas: remove comentários, tira o corpo dos heredocs e troca
    quebras de linha por ';'. `$(...)` e crases (exceto em aspas simples)
    são devolvidos à parte, pois o bash os executa.
    """
    saida, corpos, subs, pendentes = [], [], [], []
    i, n, aspas = 0, len(cmd), None
    while i < n:
        c = cmd[i]
        if c == "\\" and aspas != "'" and i + 1 < n:
            saida.append(cmd[i:i + 2])
            i += 2
            continue
        if c == "`" and aspas != "'":
            j = cmd.find("`", i + 1)
            j = n - 1 if j == -1 else j
            subs.append(cmd[i + 1:j])
            saida.append(cmd[i:j + 1])
            i = j + 1
            continue
        if aspas:
            if c == aspas:
                aspas = None
            elif aspas == '"' and c == "$":
                _registrar_subst(cmd, i, subs)
            saida.append(c)
            i += 1
            continue
        if c in "'\"":
            aspas = c
        elif c == "$":
            if cmd.startswith("$((", i):
                j = cmd.find("))", i)
                j = n if j == -1 else j + 2
                saida.append(cmd[i:j])
                i = j
                continue
            _registrar_subst(cmd, i, subs)
        elif c == "#" and (not saida or saida[-1][-1] in " \t\n;&|("):
            while i < n and cmd[i] != "\n":
                i += 1
            continue
        elif cmd.startswith("<<<", i):
            saida.append("<<<")
            i += 3
            continue
        elif cmd.startswith("<<", i):
            m = HEREDOC.match(cmd, i)
            if m:
                pendentes.append(m.group(3))
                saida.append(m.group(0))
                i = m.end()
                continue
        elif c == "\n":
            saida.append(";")
            i += 1
            for delim in pendentes:
                while i < n:
                    j = cmd.find("\n", i)
                    fim = n if j == -1 else j
                    linha = cmd[i:fim]
                    i = n if j == -1 else j + 1
                    if linha.strip() == delim:
                        break
                    corpos.append(linha)
            pendentes = []
            continue
        saida.append(c)
        i += 1
    return "".join(saida), "\n".join(corpos), subs


def _segmentos(cmd):
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    lex.commenters = ""
    segs, atual = [], []
    for tok in lex:
        if re.fullmatch(r"[;&|()]+", tok):
            if atual:
                segs.append(atual)
            atual = []
        else:
            atual.append(tok)
    if atual:
        segs.append(atual)
    return segs


def _cabeca(seg):
    """Primeiro comando real do segmento, pulando launchers, atribuições e `{`/`then`/`do`."""
    i = 0
    while i < len(seg):
        t = seg[i]
        if t in INICIOS or re.fullmatch(r"\w+=.*", t):
            i += 1
        elif t in LAUNCHERS:
            i += 1
            while i < len(seg):
                u = seg[i]
                if u in FLAGS_COM_VALOR:
                    i += 2
                elif u.startswith("-") or re.fullmatch(r"\d+(\.\d+)?[smhd]?", u) or re.fullmatch(r"\w+=.*", u):
                    i += 1
                else:
                    break
        else:
            break
    if i >= len(seg):
        return "", []
    return posixpath.basename(seg[i]), seg[i + 1:]


# ── regras ───────────────────────────────────────────────────────────────────

def _alvo_perigoso(alvo, cwd, projeto):
    if VAR_PERIGOSA.fullmatch(alvo):
        return True
    t = os.path.expanduser(alvo) if alvo.startswith("~") else alvo
    n = posixpath.normpath(t)
    if n in RELATIVOS_PERIGOSOS or n.split("/")[-1] == ".git" or all(p == ".." for p in n.split("/")):
        return True
    if not n.startswith("/"):
        if not cwd:
            return False
        n = posixpath.normpath(posixpath.join(cwd, n))
    partes = [p for p in n.split("/") if p]
    if partes[:1] == ["tmp"] and len(partes) >= 2:
        return False
    glob = bool(partes) and "*" in partes[-1]
    if len(partes) <= 2 or (glob and len(partes) <= 3):
        return True
    comparar = [n] + ([posixpath.dirname(n)] if glob else [])
    return any(p and (c == p or p.startswith(c.rstrip("/") + "/")) for c in comparar for p in (cwd, projeto))


def _rm_recursivo_perigoso(args, cwd, projeto):
    flags = [a for a in args if a.startswith("-") and a != "--"]
    recursivo = any(a == "--recursive" or (not a.startswith("--") and re.search(r"[rR]", a)) for a in flags)
    alvos = [a for a in args if not a.startswith("-")]
    return recursivo and any(_alvo_perigoso(a, cwd, projeto) for a in alvos)


def _force_push(args):
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in ("-C", "-c", "--git-dir", "--work-tree", "--namespace") else 1
    if i >= len(args) or args[i] != "push":
        return False
    return any(
        a == "--force" or re.fullmatch(r"-[a-zA-Z]*f[a-zA-Z]*", a) or re.fullmatch(r"\+\S+", a)
        for a in args[i + 1:]
    )


def _motivo_segmento(seg, corpos, cwd, projeto, prof):
    head, args = _cabeca(seg)
    if not head:
        return None

    if any(posixpath.basename(t) in CLIENTES_DB for t in seg):
        alvo = " ".join(seg) + ("\n" + corpos if "<<" in seg else "")
        if SQL_DESTRUTIVO.search(alvo):
            return "SQL destrutivo (DROP/TRUNCATE) em cliente de banco"
        if ALVO_PRODUCAO.search(alvo):
            return "cliente de banco apontando explicitamente para produção"

    if head == "rm" and _rm_recursivo_perigoso(args, cwd, projeto):
        return "rm recursivo em alvo perigoso (raiz, home, projeto, diretório atual/pai, glob, .git ou caminho de sistema/produção)"
    if head == "git" and _force_push(args):
        return "git push --force (use --force-with-lease)"
    if head.startswith("python") and "-c" in args:
        codigo = " ".join(args)
        if "execute" in codigo and SQL_DESTRUTIVO.search(codigo):
            return "SQL destrutivo (DROP/TRUNCATE) executado via python -c"
    if head == "supabase" and "db" in args and ("reset" in args or "push" in args) \
            and ("--linked" in args or "--db-url" in args):
        return "supabase db reset/push contra banco remoto"

    if prof < MAX_PROFUNDIDADE and (head in SHELLS or head in WRAPPERS):
        for a in args:
            if re.search(r"\s", a):
                m = motivo_bloqueio(a, cwd, projeto, prof + 1)
                if m:
                    return m
        if head in WRAPPERS:
            for k in range(len(args)):
                m = _motivo_segmento(args[k:], corpos, cwd, projeto, prof + 1)
                if m:
                    return m
    return None


def motivo_bloqueio(cmd, cwd="", projeto="", prof=0):
    if prof > MAX_PROFUNDIDADE:
        return None
    cmd_limpo, corpos, subs = _preprocessar(cmd)
    for sub in subs:
        m = motivo_bloqueio(sub, cwd, projeto, prof + 1)
        if m:
            return m
    try:
        segs = _segmentos(cmd_limpo)
    except ValueError:
        return None
    for seg in segs:
        m = _motivo_segmento(seg, corpos, cwd, projeto, prof)
        if m:
            return m
    return None


def main():
    try:
        payload = json.load(sys.stdin)
        cmd = (payload.get("tool_input") or {}).get("command") or ""
        cwd = payload.get("cwd") or ""
    except Exception:
        return 0
    if not cmd:
        return 0
    try:
        motivo = motivo_bloqueio(cmd, cwd, os.environ.get("CLAUDE_PROJECT_DIR", ""))
    except Exception:
        return 0
    if motivo:
        sys.stderr.write(
            f"BLOQUEADO pelo hook bloqueia_destrutivo: {motivo}.\n"
            "Se a ação é realmente intencional, peça ao usuário para executá-la manualmente.\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
