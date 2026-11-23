"""Testes dos hooks em .claude/hooks e da fiação em .claude/settings.json."""
import json
import os
import subprocess
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(RAIZ, ".claude", "hooks")


def _rodar(script, payload, cwd=None, bruto=None):
    entrada = bruto if bruto is not None else json.dumps(payload)
    return subprocess.run(
        [sys.executable, os.path.join(HOOKS, script)],
        input=entrada, capture_output=True, text=True, cwd=cwd or RAIZ, timeout=30,
    )


def _bash(cmd, cwd=None):
    payload = {"tool_name": "Bash", "tool_input": {"command": cmd}}
    if cwd:
        payload["cwd"] = cwd
    return _rodar("bloqueia_destrutivo.py", payload)


# ── bloqueia_destrutivo ──────────────────────────────────────────────────────

BLOQUEADOS = [
    "rm -rf /",
    "rm -rf .",
    "rm -rf ~",
    "rm -rf $HOME/",
    "rm -rf *",
    "rm -rf .git",
    "rm -rf /opt/orkavyn",
    "sudo rm -rf /var",
    "rm -fr /home/user",
    "echo ok && rm -rf /",
    'psql -c "DROP TABLE analises"',
    'sqlite3 gestao.db "drop table usuarios;"',
    'psql -c "TRUNCATE TABLE analises"',
    "psql -c 'DROP DATABASE postgres'",
    'psql postgres://u@db.abc.supabase.co:6543/postgres -c "select 1"',
    "psql <<EOF\nDROP TABLE analises;\nEOF",
    "python3 -c \"import sqlite3; sqlite3.connect('gestao.db').execute('DROP TABLE x')\"",
    "supabase db reset --linked",
    "git push --force origin main",
    "git push -f origin main",
    "git push origin +main",
    "git -C repo push -f origin main",
    # comentário não pode esconder as linhas seguintes
    "# limpa cache\nrm -rf ~",
    "cd /tmp # vai pro tmp\nrm -rf /opt/orkavyn",
    'ls # lista\npsql -c "DROP TABLE analises"',
    "ls # lista\ngit push --force origin main",
    "rm -rf x#y /",
    # falso início de heredoc / here-string / aritmética
    'git commit -m "doc <<EOF"\nrm -rf /',
    "cat <<< hello\nrm -rf /",
    "echo $((1<<x))\nrm -rf /",
    # wrappers
    'bash -c "rm -rf /"',
    "sh -c 'rm -rf ~'",
    'eval "rm -rf /"',
    "{ rm -rf /; }",
    "if true; then rm -rf /; fi",
    "timeout 5 rm -rf /",
    "nice -n 5 rm -rf /",
    "sudo -u root rm -rf /",
    "env -i rm -rf /",
    "echo `rm -rf /`",
    'echo "$(rm -rf /)"',
    "ssh vps 'rm -rf /opt/orkavyn'",
    'docker exec db psql -c "DROP TABLE analises"',
    'docker compose exec app psql -c "TRUNCATE analises"',
    'ssh vps psql -c "DROP TABLE x"',
    # alvos amplos
    "rm -rf ../..",
    "rm -rf ./.git",
    "rm -rf ${HOME}",
    'rm -rf "$CLAUDE_PROJECT_DIR"',
    "rm -rf $PWD",
    'rm -rf "$(pwd)"',
]

LIBERADOS = [
    "rm -rf node_modules",
    "rm -rf ./build",
    "rm -rf /tmp/orkavyn-teste",
    "rm -rf .venv",
    "rm arquivo.txt",
    'git commit -m "remove rm -rf / e DROP TABLE do exemplo"',
    "git commit -m \"$(cat <<'EOF'\nrm -rf /\nDROP TABLE x\nEOF\n)\"",
    'echo "DROP TABLE x"',
    'grep -rn "DROP TABLE" tests/',
    "pytest tests/ -k drop_table",
    "cat <<'EOF'\nTRUNCATE TABLE x\nEOF",
    'psql -c "select 1"',
    "sqlite3 gestao.db '.tables'",
    "git push origin claude/minha-branch",
    "git push --force-with-lease origin minha-branch",
    "python3 -c \"print('DROP TABLE nao executa')\"",
    "ls -la",
    # SQL/produção só contam no segmento do cliente de banco
    'sqlite3 gestao.db .tables && git log -p | grep "DROP TABLE"',
    'sqlite3 gestao.db .schema; echo "TRUNCATE TABLE x"',
    'psql -c "select 1" # drop table depois',
    "cat /opt/orkavyn/.env | head; sqlite3 gestao.db .tables",
    'grep -rn supabase.co . ; psql -c "select 1"',
    'psql <<SQL\nselect 1;\nSQL\necho "drop table" >> notas.md',
    # comentários, wrappers, crases e aritmética inofensivos
    "# rm -rf /\nls",
    "ls # rm -rf /",
    "echo 'texto com `rm -rf /` literal'",
    "bash -c 'echo ola'",
    "ssh vps 'tail -n 50 /var/log/app.log'",
    "docker compose exec app pytest -q",
    "git checkout -f push",
    "echo $((1<<3))",
    "rm -rf ../build",
    # limite documentado: SQL em script Python via heredoc não é bloqueado
    "python3 - <<'EOF'\nc.execute('DROP TABLE x')\nEOF",
]


@pytest.mark.parametrize("cmd", BLOQUEADOS)
def test_bloqueia_comando_destrutivo(cmd):
    r = _bash(cmd)
    assert r.returncode == 2, f"deveria bloquear: {cmd!r}"
    assert "BLOQUEADO" in r.stderr


@pytest.mark.parametrize("cmd", LIBERADOS)
def test_libera_comando_legitimo(cmd):
    r = _bash(cmd)
    assert r.returncode == 0, f"falso positivo: {cmd!r} -> {r.stderr}"


def test_bloqueio_ignora_entrada_invalida_ou_outra_ferramenta():
    assert _rodar("bloqueia_destrutivo.py", None, bruto="não é json").returncode == 0
    assert _rodar("bloqueia_destrutivo.py", {"tool_input": {"command": "rm -rf 'aberta"}}).returncode == 0
    assert _rodar("bloqueia_destrutivo.py", {"tool_input": {"file_path": "x.py"}}).returncode == 0


def test_rm_do_proprio_projeto_e_ancestrais_com_cwd(monkeypatch):
    monkeypatch.setenv("HOME", "/home/user")  # `~` expande conforme o HOME do ambiente (CI usa outro)
    projeto = "/home/user/meu-projeto"
    for alvo in (projeto, projeto + "/*", projeto + "/", ".", "~/meu-projeto"):
        assert _bash(f"rm -rf {alvo}", cwd=projeto).returncode == 2, alvo
    assert _bash("rm -rf build", cwd=projeto).returncode == 0
    assert _bash(f"rm -rf {projeto}/build", cwd=projeto).returncode == 0


# ── checa_sintaxe_py ─────────────────────────────────────────────────────────

def _write(caminho):
    return _rodar("checa_sintaxe_py.py", {"tool_name": "Write", "tool_input": {"file_path": str(caminho)}})


def test_sintaxe_valida_passa(tmp_path):
    f = tmp_path / "ok.py"
    f.write_text("x = 1\n")
    assert _write(f).returncode == 0


def test_sintaxe_invalida_reporta_erro(tmp_path):
    f = tmp_path / "quebrado.py"
    f.write_text("def f(:\n    pass\n")
    r = _write(f)
    assert r.returncode == 2
    assert "ERRO DE SINTAXE" in r.stderr and "quebrado.py" in r.stderr
    assert not (tmp_path / "__pycache__").exists()


def test_sintaxe_ignora_nao_py_e_ausente(tmp_path):
    md = tmp_path / "leia.md"
    md.write_text("def f(:")
    assert _write(md).returncode == 0
    assert _write(tmp_path / "nao_existe.py").returncode == 0
    assert _rodar("checa_sintaxe_py.py", None, bruto="lixo").returncode == 0


# ── lembra_testes ────────────────────────────────────────────────────────────

@pytest.fixture
def repo_tmp(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def test_lembrete_quando_ha_codigo_alterado(repo_tmp):
    (repo_tmp / "a.py").write_text("x = 1\n")
    r = _rodar("lembra_testes.py", {}, cwd=repo_tmp)
    assert r.returncode == 0
    assert "pytest" in json.loads(r.stdout)["systemMessage"]


def test_lembrete_silencioso_sem_codigo(repo_tmp):
    (repo_tmp / "notas.md").write_text("# só docs\n")
    r = _rodar("lembra_testes.py", {}, cwd=repo_tmp)
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_lembrete_respeita_stop_hook_ativo(repo_tmp):
    (repo_tmp / "a.py").write_text("x = 1\n")
    r = _rodar("lembra_testes.py", {"stop_hook_active": True}, cwd=repo_tmp)
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_lembrete_fora_de_repositorio_git(tmp_path):
    r = _rodar("lembra_testes.py", {}, cwd=tmp_path)
    assert r.returncode == 0 and r.stdout.strip() == ""


# ── settings.json ────────────────────────────────────────────────────────────

def _comandos(cfg, evento, matcher=None):
    return [
        h["command"]
        for bloco in cfg["hooks"][evento]
        if matcher is None or bloco.get("matcher") == matcher
        for h in bloco["hooks"]
    ]


def test_settings_fiacao_dos_hooks():
    with open(os.path.join(RAIZ, ".claude", "settings.json"), encoding="utf-8") as fh:
        cfg = json.load(fh)
    assert "Bash(git push *)" in cfg["permissions"]["allow"]
    assert any("bloqueia_destrutivo.py" in c for c in _comandos(cfg, "PreToolUse", "Bash"))
    assert any("checa_sintaxe_py.py" in c for c in _comandos(cfg, "PostToolUse", "Edit|Write"))
    stop = _comandos(cfg, "Stop")
    assert any("trava_testes.py" in c for c in stop)
    assert any("lembra_testes.py" in c for c in stop)
