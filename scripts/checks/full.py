"""Sensores rápidos + suite completa de pruebas. Silencioso si todo pasa.

Uso: python -m scripts.checks.full   (~2 min: levanta un Postgres embebido)
"""
import subprocess
import sys

from scripts.checks import fast


def main() -> int:
    if fast.main() != 0:
        return 1
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "--no-header", "-p", "no:cacheprovider"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode == 0:
        return 0
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    salida = (r.stdout + r.stderr).strip().splitlines()
    print("FALLA [pytest] Fallaron las pruebas. Últimas líneas:\n")
    print("\n".join(salida[-60:]))
    print("\n  Cómo: corré `python -m pytest -x -q <archivo>::<prueba>` para ver el detalle completo.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
