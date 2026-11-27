"""Ejecuta una función importable en un hijo con plazo y presupuesto de memoria."""
import importlib
import multiprocessing
import os
import pickle
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory


class TrabajoAbortado(Exception):
    """El hijo agotó un recurso o salió sin entregar su resultado."""


class ErrorDelTrabajo(Exception):
    """La función terminó con un error de dominio."""


def _hijo(modulo, nombre, args, salida, memoria_mb):
    if sys.platform == "linux":
        import resource
        limite = memoria_mb * 1024**2
        _, maximo = resource.getrlimit(resource.RLIMIT_AS)
        if maximo != resource.RLIM_INFINITY:
            limite = min(limite, maximo)
        resource.setrlimit(resource.RLIMIT_AS, (limite, limite))
        # Los parsers usan NumPy. Evitar reservas por cada CPU antes de leer el plano.
        os.environ["OPENBLAS_NUM_THREADS"] = "1"
    try:
        funcion = getattr(importlib.import_module(modulo), nombre)
        resultado = funcion(*args)
        with salida.open("wb") as f:
            pickle.dump(("ok", resultado), f, protocol=pickle.HIGHEST_PROTOCOL)
        return
    except MemoryError:
        respuesta = ("abortado", "memoria agotada")
    except Exception as error:
        respuesta = ("error", str(error))
    with salida.open("wb") as f:
        pickle.dump(respuesta, f)


def ejecutar(funcion, *args, segundos, memoria_mb):
    # El archivo temporal evita bloquear el join cuando un SVG excede el búfer de un pipe.
    with TemporaryDirectory(prefix="gsp-trabajo-") as carpeta:
        salida = Path(carpeta) / "resultado"
        hijo = multiprocessing.get_context("spawn").Process(
            target=_hijo, args=(funcion.__module__, funcion.__name__, args, salida, memoria_mb),
        )
        fin = time.monotonic() + segundos
        hijo.start()
        try:
            hijo.join(max(0, fin - time.monotonic()))
            if hijo.is_alive():
                raise TrabajoAbortado("tiempo agotado")
            if hijo.exitcode != 0 or not salida.is_file():
                raise TrabajoAbortado(f"caída del proceso (código {hijo.exitcode})")
            with salida.open("rb") as f:
                estado, valor = pickle.load(f)
        finally:
            if hijo.is_alive():
                hijo.kill()
            hijo.join()
            hijo.close()
    if estado == "abortado":
        raise TrabajoAbortado(valor)
    if estado == "error":
        raise ErrorDelTrabajo(valor)
    return valor
