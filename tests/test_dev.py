import os
import subprocess

import pytest

from scripts import dev
from tests import conftest


def _candado(carpeta, pid):
    archivo = carpeta / "postmaster.pid"
    archivo.write_text(f"{pid}\n{carpeta}\n1234\n5432\n", encoding="utf-8")
    return archivo


def test_renombra_pid_reusado_y_avisa(tmp_path, capsys):
    candado = _candado(tmp_path, os.getpid())
    contenido = candado.read_bytes()
    dato = tmp_path / "dato"
    dato.write_bytes(b"intacto")
    respaldo = dev.revisar_pid(tmp_path)
    assert not candado.exists() and respaldo.read_bytes() == contenido
    assert respaldo.name.startswith("postmaster.pid.viejo-")
    assert "no es Postgres" in capsys.readouterr().err
    assert dato.read_bytes() == b"intacto"


def test_renombra_pid_inexistente(tmp_path, capsys):
    candado = _candado(tmp_path, 10000003)
    respaldo = dev.revisar_pid(tmp_path)
    assert respaldo.exists() and not candado.exists()
    assert "no existe" in capsys.readouterr().err


def test_renombra_pid_de_postgres_sin_escucha(tmp_path, monkeypatch, capsys):
    candado = _candado(tmp_path, os.getpid())
    monkeypatch.setattr(dev, "_nombre_proceso", lambda _pid: "postgres")
    monkeypatch.setattr(dev, "_escucha", lambda _puerto, _carpeta_socket: False)
    assert dev.revisar_pid(tmp_path).exists()
    assert not candado.exists()
    assert "nada escucha" in capsys.readouterr().err


def test_postgres_real_no_se_toca_y_se_puede_reutilizar():
    server = conftest._SERVIDOR
    if server is None:
        pytest.skip("La suite usa un servidor externo sin pgdata local.")
    archivo = server.pgdata / "postmaster.pid"
    antes = archivo.read_bytes(), archivo.stat().st_mtime_ns
    assert dev.revisar_pid(server.pgdata) is None
    assert dev._arrancar_una_vez(server.pgdata) == server.get_uri()
    assert (archivo.read_bytes(), archivo.stat().st_mtime_ns) == antes


def test_reintenta_una_vez_al_ver_una_marca_nueva(tmp_path, monkeypatch, capsys):
    log = tmp_path / "log"
    intentos = []

    def arrancar(carpeta):
        intentos.append(carpeta)
        if len(intentos) == 1:
            log.write_text("database system is ready to accept connections\n", encoding="utf-8")
            raise subprocess.TimeoutExpired("pgserver", 10)
        return "postgresql://prueba"

    monkeypatch.setattr(dev, "_arrancar_una_vez", arrancar)
    assert dev.levantar_postgres(tmp_path) == "postgresql://prueba"
    assert intentos == [tmp_path, tmp_path]
    assert "Reintentando una vez" in capsys.readouterr().err


def test_no_confunde_un_log_viejo_con_recuperacion(tmp_path, monkeypatch):
    log = tmp_path / "log"
    log.write_text("database system is ready to accept connections\n", encoding="utf-8")
    intentos = []

    def arrancar(carpeta):
        intentos.append(carpeta)
        raise subprocess.TimeoutExpired("pgserver", 10)

    monkeypatch.setattr(dev, "_arrancar_una_vez", arrancar)
    monkeypatch.setattr(dev, "_ESPERA_RECUPERACION", 0)
    with pytest.raises(dev.ErrorArranque, match="Revisá el log"):
        dev.levantar_postgres(tmp_path)
    assert intentos == [tmp_path]
    assert "ready to accept connections" in log.read_text(encoding="utf-8")
