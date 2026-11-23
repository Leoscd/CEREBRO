"""Levanta el gestor en local SIN Docker: Postgres embebido (pgserver, con pgvector),
migraciones, datos demo y uvicorn con recarga.

Uso: .venv\\Scripts\\python -m scripts.dev  [--puerto 8000]
La base de desarrollo vive en data/pgdev (ignorada por git).
"""
import argparse
import csv
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from app import config

_ESPERA_RECUPERACION = 90
_LISTO = b"ready to accept connections"
_SALIDA_TIMEOUT = 75
_SALIDA_ERROR = 1


class ErrorArranque(RuntimeError):
    pass


def _nombre_proceso(pid: int) -> str | None:
    if os.name == "nt":
        comando = ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"]
        resultado = subprocess.run(
            comando, capture_output=True, text=True, errors="replace", check=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for fila in csv.reader(resultado.stdout.splitlines()):
            if len(fila) >= 2 and fila[1].strip() == str(pid):
                return fila[0].strip()
        return None
    if sys.platform.startswith("linux"):
        try:
            return Path(f"/proc/{pid}/comm").read_text(encoding="utf-8", errors="replace").strip()
        except FileNotFoundError:
            return None
    resultado = subprocess.run(["ps", "-p", str(pid), "-o", "comm="], capture_output=True,
                              text=True, timeout=5, check=False)
    return Path(resultado.stdout.strip()).name or None


def _escucha(puerto: int, carpeta_socket: str) -> bool:
    if carpeta_socket and hasattr(socket, "AF_UNIX") and os.name != "nt":
        ruta = str(Path(carpeta_socket) / f".s.PGSQL.{puerto}")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as canal:
                canal.settimeout(0.5)
                canal.connect(ruta)
            return True
        except OSError:
            return False
    for host in ("127.0.0.1", "::1"):
        try:
            with socket.create_connection((host, puerto), timeout=0.5):
                return True
        except OSError:
            continue
    return False


def revisar_pid(carpeta: Path) -> Path | None:
    """Conserva como respaldo el PID obsoleto y deja intacto un servidor activo."""
    candado = carpeta / "postmaster.pid"
    if candado.is_symlink():
        raise ErrorArranque(f"El archivo {candado} es un enlace. Revisalo antes de reiniciar.")
    try:
        contenido = candado.read_bytes()
    except FileNotFoundError:
        return None
    try:
        lineas = contenido.decode("utf-8", errors="replace").splitlines()
        pid, puerto = int(lineas[0]), int(lineas[3])
        if pid <= 0 or not 0 < puerto <= 65535:
            raise ValueError("PID o puerto fuera de rango")
    except (IndexError, ValueError) as error:
        raise ErrorArranque(f"No pude interpretar {candado}. Revisalo antes de reiniciar.") from error

    try:
        nombre = _nombre_proceso(pid)
    except (OSError, subprocess.SubprocessError) as error:
        raise ErrorArranque(f"No pude verificar el PID de Postgres ({pid}). Revisá {candado}.") from error
    carpeta_socket = lineas[4].strip() if len(lineas) > 4 else ""
    if nombre is None:
        motivo = f"el PID {pid} no existe"
    elif nombre.casefold() not in {"postgres", "postgres.exe", "postmaster", "postmaster.exe"}:
        motivo = f"el PID {pid} no es Postgres ({nombre})"
    elif not _escucha(puerto, carpeta_socket):
        motivo = f"nada escucha en el puerto {puerto}"
    else:
        return None

    try:
        if candado.read_bytes() != contenido:
            return None
        sufijo = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        respaldo = candado.with_name(f"{candado.name}.viejo-{sufijo}")
        if respaldo.exists():
            raise FileExistsError(respaldo)
        candado.rename(respaldo)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ErrorArranque(f"No pude resguardar {candado}. Revisá sus permisos.") from error
    print(f"Postgres: candado viejo ({motivo}). Se conservó en {respaldo}.", file=sys.stderr, flush=True)
    return respaldo


def _salida_es_timeout(error: subprocess.CalledProcessError) -> bool:
    salida = f"{error.stdout or ''} {error.stderr or ''}".lower()
    return "did not start in time" in salida or "timed out" in salida


def _arranque_interno(carpeta: Path) -> int:
    import pgserver

    try:
        servidor = pgserver.get_server(str(carpeta), cleanup_mode=None)
        print(servidor.get_uri())
        return 0
    except subprocess.TimeoutExpired:
        return _SALIDA_TIMEOUT
    except subprocess.CalledProcessError as error:
        return _SALIDA_TIMEOUT if _salida_es_timeout(error) else _SALIDA_ERROR


def _arrancar_una_vez(carpeta: Path) -> str:
    # Un proceso nuevo evita que pgserver reutilice un objeto incompleto tras un timeout.
    comando = [sys.executable, "-m", "scripts.dev", "--arranque-interno", str(carpeta)]
    resultado = subprocess.run(comando, capture_output=True, text=True, errors="replace",
                               timeout=60, check=False)
    if resultado.returncode == _SALIDA_TIMEOUT:
        raise subprocess.TimeoutExpired(comando, 10)
    url = resultado.stdout.strip()
    if resultado.returncode != 0 or not url.startswith("postgresql://"):
        raise ErrorArranque(f"No se pudo iniciar Postgres. Revisá el log {carpeta / 'log'} y volvé a ejecutar scripts.dev.")
    return url


def _esperar_recuperacion(log: Path, posicion: int) -> bool:
    hasta = time.monotonic() + _ESPERA_RECUPERACION
    cola = b""
    while True:
        try:
            with log.open("rb") as archivo:
                if os.fstat(archivo.fileno()).st_size < posicion:
                    posicion, cola = 0, b""
                archivo.seek(posicion)
                while bloque := archivo.read(64 * 1024):
                    datos = cola + bloque
                    if _LISTO in datos:
                        return True
                    if time.monotonic() >= hasta:
                        return False
                    cola = datos[-(len(_LISTO) - 1):]
                posicion = archivo.tell()
        except FileNotFoundError:
            posicion, cola = 0, b""
        restante = hasta - time.monotonic()
        if restante <= 0:
            return False
        time.sleep(min(1, restante))


def levantar_postgres(carpeta: Path) -> str:
    revisar_pid(carpeta)
    log = carpeta / "log"
    try:
        posicion = log.stat().st_size
    except FileNotFoundError:
        posicion = 0
    try:
        return _arrancar_una_vez(carpeta)
    except subprocess.TimeoutExpired:
        print("Postgres tardó más de lo esperado. Esperando que termine la recuperación…",
              file=sys.stderr, flush=True)
    if not _esperar_recuperacion(log, posicion):
        raise ErrorArranque(f"Postgres no quedó listo. Revisá el log {log} y volvé a ejecutar scripts.dev.")
    print("Postgres informó que está listo. Reintentando una vez.", file=sys.stderr, flush=True)
    try:
        return _arrancar_una_vez(carpeta)
    except subprocess.TimeoutExpired as error:
        raise ErrorArranque(f"Postgres no respondió al reintento. Revisá el log {log} y volvé a ejecutar scripts.dev.") from error


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--puerto", type=int, default=int(os.getenv("PORT", "8000")))
    ap.add_argument("--arranque-interno", type=Path, help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.arranque_interno is not None:
        raise SystemExit(_arranque_interno(args.arranque_interno))

    carpeta = config.DATA_DIR / "pgdev"
    carpeta.mkdir(parents=True, exist_ok=True)
    try:
        url = levantar_postgres(carpeta)
    except (OSError, ErrorArranque) as error:
        raise SystemExit(str(error)) from error
    os.environ["DATABASE_URL"] = url
    config.DATABASE_URL = url

    from scripts import seed_demo

    seed_demo.main()

    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=args.puerto, reload=False)


if __name__ == "__main__":
    main()
