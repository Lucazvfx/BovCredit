"""Stop: lembrete não bloqueante de rodar testes quando há código alterado.

Nunca bloqueia (sempre exit 0). Só fala se `git status` mostrar arquivo de
código modificado; conversa, análise e documentação (.md) ficam em silêncio.
O aviso sai como systemMessage (visível ao usuário).
"""
import json
import os
import subprocess
import sys

EXTENSOES_CODIGO = {".py", ".html", ".js", ".css", ".sql"}


def _eh_codigo(caminho):
    base = os.path.basename(caminho)
    return os.path.splitext(base)[1] in EXTENSOES_CODIGO or (
        base.startswith("requirements") and base.endswith(".txt")
    )


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    if payload.get("stop_hook_active"):
        return 0

    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, timeout=10
        )
    except Exception:
        return 0
    if status.returncode != 0:
        return 0

    alterados = [l[3:].strip().strip('"') for l in status.stdout.splitlines() if len(l) > 3]
    codigo = [a for a in alterados if _eh_codigo(a)]
    if not codigo:
        return 0

    amostra = ", ".join(codigo[:3]) + (f" (+{len(codigo) - 3})" if len(codigo) > 3 else "")
    print(json.dumps({
        "systemMessage": (
            f"Lembrete: {len(codigo)} arquivo(s) de código alterado(s) [{amostra}]. "
            "Se ainda não rodou, considere `python -m pytest -q` (ou os testes afetados) antes de encerrar."
        )
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
