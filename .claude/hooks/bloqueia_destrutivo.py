"""PreToolUse (Bash): bloqueia comandos destrutivos claros (exit 2).

Só dispara quando o comando *executa* a ação. Texto dentro de aspas, mensagem
de commit, heredoc ou argumento de grep/echo/pytest não conta. Qualquer falha
de leitura/parsing libera o comando (exit 0): o hook nunca trava o ambiente.
"""
import json
import os
import posixpath
import re
import shlex
import sys

PREFIXOS = {"sudo", "env", "command", "nohup", "time", "exec", "nice"}
CLIENTES_DB = {"psql", "sqlite3", "mysql", "mariadb", "usql", "pgcli"}
SQL_DESTRUTIVO = re.compile(r"\b(drop\s+(table|database|schema)|truncate(\s+table)?\s+[\w\"])", re.I)
ALVO_PRODUCAO = re.compile(r"supabase\.(co|com)|pooler\.supabase|credito\.orkavyn\.tech|/opt/orkavyn", re.I)
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1")
RELATIVOS_PERIGOSOS = {".", "./", "..", "../", "*", "./*", ".*", ".git", ".git/", "~", "~/", "~/*", "$HOME", "$HOME/", "$HOME/*"}


def _separar_heredocs(cmd):
    """Remove o corpo dos heredocs; devolve (comando_sem_corpos, texto_dos_corpos)."""
    saida, corpos, delim = [], [], None
    for linha in cmd.split("\n"):
        if delim is not None:
            if linha.strip() == delim:
                delim = None
            else:
                corpos.append(linha)
            continue
        saida.append(linha)
        achou = HEREDOC.search(linha)
        if achou:
            delim = achou.group(2)
    return "\n".join(saida), "\n".join(corpos)


def _newlines_fora_de_aspas(cmd):
    """Troca quebras de linha fora de aspas por ';' (separador de comando)."""
    saida, aspas, escape = [], None, False
    for c in cmd:
        if escape:
            escape = False
        elif c == "\\" and aspas != "'":
            escape = True
        elif aspas:
            if c == aspas:
                aspas = None
        elif c in "'\"":
            aspas = c
        elif c == "\n":
            c = ";"
        saida.append(c)
    return "".join(saida)


def _segmentos(cmd):
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
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
    i = 0
    while i < len(seg) and (seg[i] in PREFIXOS or re.fullmatch(r"\w+=.*", seg[i])):
        i += 1
    if i >= len(seg):
        return "", []
    return posixpath.basename(seg[i]), seg[i + 1:]


def _alvo_perigoso(alvo):
    if alvo in RELATIVOS_PERIGOSOS:
        return True
    if not alvo.startswith("/"):
        return False
    partes = [p for p in posixpath.normpath(alvo).split("/") if p]
    if partes and partes[0] == "tmp" and len(partes) >= 2 and "*" not in partes[1:2]:
        return False
    return len(partes) <= 2 or (len(partes) == 3 and "*" in partes[-1])


def _rm_recursivo_perigoso(args):
    flags = [a for a in args if a.startswith("-") and a != "--"]
    recursivo = any(a == "--recursive" or (not a.startswith("--") and re.search(r"[rR]", a)) for a in flags)
    alvos = [a for a in args if not a.startswith("-")]
    return recursivo and any(_alvo_perigoso(a) for a in alvos)


def _force_push(args):
    if "push" not in args:
        return False
    for a in args:
        if a == "--force" or re.fullmatch(r"-[a-zA-Z]*f[a-zA-Z]*", a) or re.fullmatch(r"\+\S+", a):
            return True
    return False


def motivo_bloqueio(cmd):
    cmd_limpo, corpos = _separar_heredocs(cmd)
    try:
        segs = _segmentos(_newlines_fora_de_aspas(cmd_limpo))
    except ValueError:
        return None
    pecas = [_cabeca(s) for s in segs]
    cliente_db = any(h in CLIENTES_DB for h, _ in pecas)
    texto_completo = cmd + "\n" + corpos

    for head, args in pecas:
        if head == "rm" and _rm_recursivo_perigoso(args):
            return "rm recursivo em alvo perigoso (raiz, home, diretório atual/pai, glob, .git ou caminho de sistema/produção)"
        if head == "git" and _force_push(args):
            return "git push --force (use --force-with-lease)"
        if head in ("python", "python3") and "-c" in args:
            codigo = " ".join(args)
            if "execute" in codigo and SQL_DESTRUTIVO.search(codigo):
                return "SQL destrutivo (DROP/TRUNCATE) executado via python -c"
        if head == "supabase" and "db" in args and ("reset" in args or "push" in args) \
                and ("--linked" in args or "--db-url" in args):
            return "supabase db reset/push contra banco remoto"

    if cliente_db and SQL_DESTRUTIVO.search(texto_completo):
        return "SQL destrutivo (DROP/TRUNCATE) em cliente de banco"
    if cliente_db and ALVO_PRODUCAO.search(texto_completo):
        return "cliente de banco apontando explicitamente para produção"
    return None


def main():
    try:
        payload = json.load(sys.stdin)
        cmd = (payload.get("tool_input") or {}).get("command") or ""
    except Exception:
        return 0
    if not cmd:
        return 0
    try:
        motivo = motivo_bloqueio(cmd)
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
