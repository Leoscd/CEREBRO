"""Hook PreToolUse (Claude Code): bloquea acciones destructivas a nivel infraestructura.

No confía en el prompt: lee la acción que el agente va a ejecutar y decide.
- deny: se bloquea y el agente recibe el motivo.
- ask:  se le pregunta a Leo antes de ejecutar.
- sin salida: se permite.
Solo usa la biblioteca estándar (corre con cualquier Python).
"""
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
LOCK = RAIZ / "scripts" / "checks" / "migraciones.lock"

DENEGAR = [
    (r"\bgit\s+push\b.*(\s--force\b|\s-f\b|\s--force-with-lease\b|\s\+\S)", "push forzado: reescribe historia remota."),
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard descarta trabajo sin vuelta atrás."),
    (r"\bgit\s+clean\s+-\w*f", "git clean -f borra archivos no versionados."),
    (r"\bgit\s+branch\s+(?-i:-D)\b","borrar ramas a la fuerza: hacelo a mano si hace falta."),
    (r"\brm\s+-\w*r\w*\s+(/|~|\.|\*|app|data|tests|\.git)(\s|$|/)", "borrado recursivo de una carpeta clave."),
    (r"Remove-Item\b.*-Recurse.*\b(app|data|tests|\.git)\b", "borrado recursivo de una carpeta clave."),
    (r"\b(DROP\s+(TABLE|DATABASE|SCHEMA)|TRUNCATE\s+)", "SQL destructivo: los cambios de esquema van en una migración nueva."),
    (r"--dangerously-bypass-approvals-and-sandbox", "Codex sin sandbox: no desde una sesión de agente."),
]

PREGUNTAR = [
    (r"\bgh\s+pr\s+merge\b", "El merge lo decide Leo."),
    (r"\bgit\s+push\b.*\b(main|master)\b", "main se actualiza solo por PR."),
    (r"\bgh\s+repo\s+(create|delete|edit)\b", "Cambia el repositorio en GitHub."),
    (r"\bgh\s+api\b.*-X\s*(DELETE|PUT|PATCH)", "Escritura directa en la API de GitHub."),
    (r"(\./)?scripts/deploy\.sh|\bdocker\s+compose\b.*\bup\b", "Despliegue."),
]


def _salir(decision: str, motivo: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                             "permissionDecisionReason": f"[guardia] {motivo}"}}))
    sys.exit(0)


def _sellada(ruta: str) -> bool:
    p = Path(ruta.replace("\\", "/"))
    if "app/db/migraciones" not in p.as_posix() or not LOCK.exists():
        return False
    return any(ln.split()[0] == p.name for ln in LOCK.read_text(encoding="utf-8").splitlines()
               if ln.strip() and not ln.startswith("#"))


def main() -> None:
    try:
        evento = json.load(sys.stdin)
    except ValueError:
        return
    herramienta = evento.get("tool_name", "")
    entrada = evento.get("tool_input", {}) or {}

    if herramienta in ("Bash", "PowerShell"):
        cmd = entrada.get("command", "")
        for patron, motivo in DENEGAR:
            if re.search(patron, cmd, re.I):
                _salir("deny", motivo)
        for patron, motivo in PREGUNTAR:
            if re.search(patron, cmd, re.I):
                _salir("ask", motivo)

    if herramienta in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        ruta = entrada.get("file_path", "") or entrada.get("notebook_path", "")
        if _sellada(ruta):
            _salir("deny", "Esa migración ya está sellada (aplicada). Creá una nueva con el número siguiente.")
        if ruta.replace("\\", "/").endswith("scripts/checks/migraciones.lock"):
            _salir("ask", "Sellar migraciones: usá `python -m scripts.harness sellar` después del merge.")


if __name__ == "__main__":
    main()
