"""Puerta de validación: solo las ramas `harness/...` (de Leo) pueden tocar el harness.

Se define por lista blanca y no por "ramas de agentes" para no depender de cómo nombre
la rama cada plataforma (Codex cloud, Codex local, otro agente).

El agente que genera código nunca edita sus propias instrucciones permanentes ni los
sensores que lo controlan. Si cree que hace falta una regla nueva, la propone en
harness/candidatos/ y un humano la promueve en una rama `harness/...`.

Uso (CI): python -m scripts.checks.protegidos --base origin/main --rama "$RAMA"
Silencioso si está todo bien.
"""
from __future__ import annotations

import argparse
import subprocess
import sys

PREFIJOS_HUMANO = ("harness/",)

PROTEGIDOS = (
    "AGENTS.md",
    "CLAUDE.md",
    ".agents/",
    ".claude/",
    ".codex/",
    ".github/",
    "scripts/checks/",
    "scripts/hooks/",
    "scripts/harness.py",
    "harness/README.md",
    "harness/rubricas/",
    "harness/log.md",
    "harness/evals/",
)


def archivos_cambiados(base: str) -> list[str]:
    r = subprocess.run(["git", "diff", "--name-only", f"{base}...HEAD"], capture_output=True, text=True, check=True)
    return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]


def violaciones(archivos: list[str]) -> list[str]:
    return [a for a in archivos if any(a == p or (p.endswith("/") and a.startswith(p)) for p in PROTEGIDOS)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--rama", default="")
    args = ap.parse_args()
    if args.rama.startswith(PREFIJOS_HUMANO):
        return 0
    malos = violaciones(archivos_cambiados(args.base))
    if not malos:
        return 0
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"FALLA [protegidos] La rama '{args.rama}' modificó archivos del harness (solo ramas harness/... pueden):\n")
    print("\n".join(f"  - {a}" for a in malos))
    print("\n  Cómo: revertí esos cambios en esta rama. Si proponés una regla o skill nueva, escribila en\n"
          "  harness/candidatos/C-NNN-*.md; la promueve un humano después de validarla.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
