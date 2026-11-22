import json
import subprocess
import sys


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    if payload.get("stop_hook_active"):
        return 0

    status = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
    )
    arquivos_py = [
        linha[3:]
        for linha in status.stdout.splitlines()
        if linha.strip().endswith(".py")
    ]
    if not arquivos_py:
        return 0

    resultado = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", "--tb=short"],
        capture_output=True,
        text=True,
    )

    if resultado.returncode != 0:
        saida = (resultado.stdout + "\n" + resultado.stderr).strip()
        linhas = saida.splitlines()[-40:]
        sys.stderr.write(
            "TRAVA DE TESTES: pytest falhou. Corrija os erros antes de concluir:\n\n"
            + "\n".join(linhas)
            + "\n"
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
