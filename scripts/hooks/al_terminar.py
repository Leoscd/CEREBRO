"""Hook Stop (Claude Code): antes de dar el turno por terminado, corre los sensores rápidos
si hay cambios sin commitear en código. Éxito silencioso; si falla, devuelve el detalle
al agente (exit 2) para que lo corrija. Nunca bloquea dos veces seguidas.
"""
import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def main() -> int:
    try:
        evento = json.load(sys.stdin)
    except ValueError:
        evento = {}
    if evento.get("stop_hook_active"):
        return 0
    estado = subprocess.run(["git", "status", "--porcelain"], cwd=RAIZ, capture_output=True, text=True)
    cambios = [ln[3:] for ln in estado.stdout.splitlines()]
    if not any(c.endswith((".py", ".sql")) or c.startswith(("app/", "tests/", "scripts/")) for c in cambios):
        return 0
    py = RAIZ / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    r = subprocess.run([str(py if py.exists() else sys.executable), "-m", "scripts.checks.fast"], cwd=RAIZ,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode == 0:
        return 0
    sys.stderr.write("Los sensores rápidos fallaron sobre los cambios actuales:\n\n" + r.stdout[-6000:])
    return 2


if __name__ == "__main__":
    sys.exit(main())
