"""CLI del harness: salidas cortas para que los agentes gasten pocos tokens.

python -m scripts.harness estado
python -m scripts.harness nueva "Título"
python -m scripts.harness codex T-001 [--sin-pr] [--modelo X]
python -m scripts.harness auditar 12
python -m scripts.harness sellar
python -m scripts.harness podar [--dias 30]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

from scripts.checks import fast, protegidos

RAIZ = Path(__file__).resolve().parents[1]
TAREAS = RAIZ / "harness" / "tareas"
CANDIDATOS = RAIZ / "harness" / "candidatos"
CORRIDAS = RAIZ / ".harness-runs"
DOCS = RAIZ / "docs"
WORKTREES = RAIZ.parent / f"{RAIZ.name}-worktrees"
DOCS_VENCEN_DIAS = 90

SENSIBLES = ("app/permisos.py", "app/security.py", "app/db/migraciones/", "app/routers/",
             "app/services/auditoria.py", "app/services/", "app/templates/")
IGNORAR_DIFF = (".lock", ".min.js", ".min.css", ".png", ".jpg", ".svg", ".ico", ".woff", ".woff2")
TOPE_ARCHIVO, TOPE_TOTAL = 250, 1200


def _git(*args: str, cwd: Path = RAIZ, check: bool = True) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          check=check).stdout.strip()


def _frontmatter(p: Path) -> dict[str, str]:
    texto = p.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---", texto, re.S)
    datos = {}
    for linea in (m.group(1).splitlines() if m else []):
        if ":" in linea:
            k, v = linea.split(":", 1)
            datos[k.strip()] = re.sub(r"\s+#.*$", "", v).strip().strip("\"'")
    return datos


def _tareas() -> list[Path]:
    return sorted(p for p in TAREAS.glob("T-*.md"))


def _buscar_tarea(ident: str) -> Path:
    ident = ident.upper() if ident.lower().startswith("t-") else f"T-{int(ident):03d}"
    hallados = [p for p in _tareas() if p.name.startswith(ident + "-") or p.stem == ident]
    if not hallados:
        sys.exit(f"No encontré la tarea {ident} en {TAREAS.relative_to(RAIZ)}")
    return hallados[0]


def _slug(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:40]


# ---------- estado ----------

def cmd_estado(_args) -> None:
    hoy = dt.date.today()
    print("TAREAS")
    for p in _tareas():
        fm = _frontmatter(p)
        pr = f" PR {fm['pr']}" if fm.get("pr") else ""
        print(f"  {fm.get('id', p.stem):6} {fm.get('estado', '?'):12} {fm.get('titulo', '')}{pr}")
    propuestos = [p.name for p in CANDIDATOS.glob("C-*.md") if _frontmatter(p).get("estado") == "propuesto"]
    if propuestos:
        print(f"CANDIDATOS por validar: {', '.join(propuestos)}")
    sin_sellar = [a.name for a in sorted(fast.MIGRACIONES.glob('*.sql')) if a.name not in fast.leer_lock()]
    if sin_sellar:
        print(f"MIGRACIONES sin sellar (sellar tras el merge): {', '.join(sin_sellar)}")
    vencidos = []
    for d in sorted(DOCS.rglob("*.md")):
        m = re.search(r"revisado:\s*(\d{4}-\d{2}-\d{2})", d.read_text(encoding="utf-8")[:600])
        if not m:
            vencidos.append(f"{d.relative_to(RAIZ).as_posix()} (sin 'revisado:')")
        elif (hoy - dt.date.fromisoformat(m.group(1))).days > DOCS_VENCEN_DIAS:
            vencidos.append(f"{d.relative_to(RAIZ).as_posix()} ({m.group(1)})")
    if vencidos:
        print(f"DOCS a revisar (memoria semántica > {DOCS_VENCEN_DIAS} días): {'; '.join(vencidos)}")


# ---------- nueva ----------

def cmd_nueva(args) -> None:
    numeros = [int(m.group(1)) for p in _tareas() if (m := re.match(r"T-(\d+)", p.name))]
    n = f"T-{(max(numeros) + 1) if numeros else 1:03d}"
    slug = _slug(args.titulo)
    plantilla = (TAREAS / "_plantilla.md").read_text(encoding="utf-8")
    texto = (plantilla.replace("T-NNN-SLUG", f"{n}-{slug}").replace("T-NNN", n)
             .replace("TITULO", args.titulo).replace("FECHA", dt.date.today().isoformat()))
    destino = TAREAS / f"{n}-{slug}.md"
    destino.write_text(texto, encoding="utf-8")
    print(destino.relative_to(RAIZ).as_posix())


# ---------- codex (ejecución local en un worktree) ----------

def cmd_codex(args) -> None:
    tarea = _buscar_tarea(args.tarea)
    fm = _frontmatter(tarea)
    rama, ident = fm["rama"], fm["id"]
    if fm.get("estado") not in ("lista", "en-curso"):
        sys.exit(f"{ident} está en estado '{fm.get('estado')}'. Pasala a 'lista' antes de ejecutarla.")
    if not shutil.which("codex"):
        sys.exit("No encuentro el comando `codex` en el PATH.")
    hay_remoto = bool(_git("remote", check=False))
    base = "origin/main" if hay_remoto else "main"
    if hay_remoto:
        _git("fetch", "origin", "main")
    wt = WORKTREES / ident
    if not wt.exists():
        WORKTREES.mkdir(exist_ok=True)
        _git("worktree", "add", "-b", rama, str(wt), base)
    CORRIDAS.mkdir(exist_ok=True)
    salida = CORRIDAS / f"{ident}-{dt.datetime.now():%Y%m%d-%H%M%S}.md"
    py = RAIZ / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    rel = tarea.relative_to(RAIZ).as_posix()
    pedido = (
        f"Ejecutá la tarea {rel} siguiendo .agents/skills/ejecutar-tarea/SKILL.md. "
        f"Ya estás en la rama {rama}. Usá este Python para sensores y pruebas: {py}. "
        "Hacé commits en la rama pero NO hagas push ni abras el PR: eso lo hace el script. "
        "Tu mensaje final tiene que ser el cuerpo del PR completo según .github/pull_request_template.md."
    )
    cmd = ["codex", "exec", "-C", str(wt), "--sandbox", "workspace-write", "-o", str(salida)]
    if args.modelo:
        cmd += ["-m", args.modelo]
    print(f"Codex trabajando en {wt} (rama {rama})…")
    r = subprocess.run([*cmd, pedido])
    if r.returncode != 0:
        sys.exit(f"Codex terminó con código {r.returncode}. Revisá {wt}.")
    commits = _git("rev-list", "--count", f"{base}..HEAD", cwd=wt)
    if commits == "0":
        sys.exit(f"Codex no dejó commits en {rama}. Mirá {wt} y {salida.relative_to(RAIZ)}.")
    s = subprocess.run([str(py), "-m", "scripts.checks.fast"], cwd=wt, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if s.returncode != 0:
        print("Atención: los sensores rápidos fallan en la rama (CI lo va a marcar):\n" + s.stdout[-3000:])
    if args.sin_pr or not hay_remoto:
        print(f"Listo: {commits} commit(s) en {rama}. Cuerpo del PR en {salida.relative_to(RAIZ)}.")
        return
    _git("push", "-u", "origin", rama, cwd=wt)
    url = subprocess.run(["gh", "pr", "create", "--base", "main", "--head", rama,
                          "--title", f"{ident}: {fm.get('titulo', '')}", "--body-file", str(salida)],
                         cwd=wt, capture_output=True, text=True, encoding="utf-8")
    print(url.stdout.strip() or url.stderr.strip())


# ---------- auditar (paquete compacto para el evaluador) ----------

def _prioridad(ruta: str) -> int:
    for i, p in enumerate(SENSIBLES):
        if ruta.startswith(p):
            return i
    return len(SENSIBLES) + (0 if ruta.startswith("tests/") else 1)


def rutas_tocar(texto: str) -> list[str]:
    """Rutas entre backticks de "- Tocar:" hasta "- No tocar:" (puede ocupar varios renglones). H-006."""
    bloque = re.search(r"^- Tocar:(.*?)(?=^- No tocar:|^## |\Z)", texto, re.M | re.S)
    if not bloque:
        return []
    return [r for r in re.findall(r"`([^`]+)`", bloque.group(1)) if "/" in r or "." in r]


def cmd_auditar(args) -> None:
    campos = "number,title,headRefName,baseRefName,body,files,statusCheckRollup,additions,deletions,isDraft"
    pr = json.loads(subprocess.run(["gh", "pr", "view", str(args.pr), "--json", campos], cwd=RAIZ,
                                   capture_output=True, text=True, encoding="utf-8", check=True).stdout)
    print(f"# PR #{pr['number']} · {pr['title']}  ({pr['headRefName']} → {pr['baseRefName']}, "
          f"+{pr['additions']} −{pr['deletions']}{', BORRADOR' if pr['isDraft'] else ''})\n")

    checks = pr.get("statusCheckRollup") or []
    estados = [f"{c.get('name') or c.get('context')}: {c.get('conclusion') or c.get('state') or c.get('status')}"
               for c in checks]
    print("## CI\n" + ("\n".join(f"- {e}" for e in estados) if estados else "- sin checks todavía") + "\n")

    m = re.search(r"T-\d{3}", pr["title"] + " " + pr["headRefName"], re.I)
    tocar = []
    if m:
        tarea = _buscar_tarea(m.group(0))
        texto = tarea.read_text(encoding="utf-8")
        texto = texto.split("## Dictamen del auditor")[0]
        print(f"## Tarea ({tarea.relative_to(RAIZ).as_posix()})\n{texto.strip()}\n")
        tocar = rutas_tocar(texto)
    else:
        print("## Tarea\n- El PR no menciona T-NNN: pedile a Codex que la enlace.\n")

    archivos = [f["path"] for f in pr["files"]]
    print("## Archivos")
    for f in sorted(pr["files"], key=lambda f: _prioridad(f["path"])):
        marca = ""
        if protegidos.violaciones([f["path"]]):
            marca = "  ⚠ PROTEGIDO"
        elif tocar and not f["path"].startswith("harness/") and not any(f["path"].startswith(t) for t in tocar):
            marca = "  ⚠ fuera de 'Tocar'"
        print(f"- {f['path']} (+{f['additions']} −{f['deletions']}){marca}")
    print()

    print("## Cuerpo del PR\n" + (pr.get("body") or "(vacío)").strip() + "\n")

    diff = subprocess.run(["gh", "pr", "diff", str(args.pr)], cwd=RAIZ, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=True).stdout
    bloques = re.split(r"(?m)^(?=diff --git )", diff)
    porruta = {}
    for b in bloques:
        mm = re.match(r"diff --git a/(\S+) b/", b)
        if mm:
            porruta[mm.group(1)] = b
    print("## Diff (sensibles primero, recortado)")
    total = 0
    for ruta in sorted(porruta, key=_prioridad):
        if ruta.endswith(IGNORAR_DIFF) or ruta.startswith("harness/tareas/"):
            print(f"\n[omitido] {ruta}")
            continue
        lineas = porruta[ruta].splitlines()
        if total >= TOPE_TOTAL:
            print(f"\n[sin mostrar por tope total] {ruta} ({len(lineas)} líneas)")
            continue
        corte = min(TOPE_ARCHIVO, TOPE_TOTAL - total)
        print("\n" + "\n".join(lineas[:corte]))
        if len(lineas) > corte:
            print(f"[… {len(lineas) - corte} líneas más de {ruta}: `gh pr diff {args.pr}` o Read con offset]")
        total += min(len(lineas), corte)
    faltan = set(archivos) - set(porruta)
    if faltan:
        print(f"\n[sin diff de texto] {', '.join(sorted(faltan))}")


# ---------- sellar / podar ----------

def cmd_sellar(_args) -> None:
    previos = fast.leer_lock()
    archivos = sorted(fast.MIGRACIONES.glob("*.sql"))
    lineas = ["# Migraciones selladas (ya aplicadas en producción o en main). Solo un humano sella:",
              "# python -m scripts.harness sellar"]
    for a in archivos:
        sha = previos.get(a.name) or fast._sha(a)
        lineas.append(f"{a.name} {sha}")
    fast.LOCK_MIGRACIONES.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    nuevas = [a.name for a in archivos if a.name not in previos]
    print(f"Selladas: {', '.join(nuevas)}" if nuevas else "No había migraciones nuevas.")


def cmd_podar(args) -> None:
    if not CORRIDAS.exists():
        return
    limite = dt.datetime.now().timestamp() - args.dias * 86400
    viejos = [p for p in CORRIDAS.iterdir() if p.is_file() and p.stat().st_mtime < limite]
    for p in viejos:
        p.unlink()
    if viejos:
        print(f"Borradas {len(viejos)} corridas de más de {args.dias} días.")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="harness")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("estado").set_defaults(f=cmd_estado)
    p = sub.add_parser("nueva")
    p.add_argument("titulo")
    p.set_defaults(f=cmd_nueva)
    p = sub.add_parser("codex")
    p.add_argument("tarea")
    p.add_argument("--sin-pr", action="store_true")
    p.add_argument("--modelo", default="")
    p.set_defaults(f=cmd_codex)
    p = sub.add_parser("auditar")
    p.add_argument("pr", type=int)
    p.set_defaults(f=cmd_auditar)
    sub.add_parser("sellar").set_defaults(f=cmd_sellar)
    p = sub.add_parser("podar")
    p.add_argument("--dias", type=int, default=30)
    p.set_defaults(f=cmd_podar)
    args = ap.parse_args()
    args.f(args)


if __name__ == "__main__":
    main()
