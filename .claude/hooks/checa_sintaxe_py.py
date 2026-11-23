"""PostToolUse (Edit|Write): confere a sintaxe de arquivos .py com py_compile.

Erro de sintaxe -> exit 2 (a mensagem volta para o Claude; a edição já foi
feita, então não desfaz nada). Qualquer outra falha (python indisponível,
timeout, arquivo ausente, erro de ambiente) -> exit 0, sem ruído.
"""
import json
import os
import subprocess
import sys
import tempfile

ERROS_DE_SINTAXE = ("SyntaxError", "IndentationError", "TabError")


def main():
    try:
        payload = json.load(sys.stdin)
        caminho = (payload.get("tool_input") or {}).get("file_path") or ""
    except Exception:
        return 0
    if not caminho.endswith(".py") or not os.path.isfile(caminho):
        return 0

    # PYTHONPYCACHEPREFIX evita gravar __pycache__/.pyc ao lado do código.
    env = {**os.environ, "PYTHONPYCACHEPREFIX": os.path.join(tempfile.gettempdir(), "orkavyn-pyc")}
    try:
        r = subprocess.run(
            [sys.executable, "-m", "py_compile", caminho],
            capture_output=True, text=True, timeout=15, env=env,
        )
    except Exception:
        return 0

    if r.returncode != 0 and any(e in r.stderr for e in ERROS_DE_SINTAXE):
        sys.stderr.write(f"ERRO DE SINTAXE em {caminho}:\n{r.stderr.strip()}\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
