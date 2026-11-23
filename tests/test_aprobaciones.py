import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, asynccontextmanager
from threading import Barrier

import pytest
from agents import Agent
from pydantic import BaseModel, Field

from app.agentes import aprobaciones
from app.agentes.modelo_falso import ModeloFalso
from app.db import pool
from app.permisos import puede_gestionar_precios
from tests.conftest import csrf_de


@pytest.fixture
def turno(db, mundo, monkeypatch):
    user = mundo["ana"]
    proyecto = mundo["p1"]
    empresa = user["empresa_id"]
    consultas = []
    db.execute(
        """INSERT INTO usuario_areas(usuario_id,area_id) SELECT %s,id FROM areas
            WHERE empresa_id=%s AND codigo='gestion_administrativa'""", (user["id"], empresa),
    )
    conv = db.execute(
        """INSERT INTO conversaciones(empresa_id,proyecto_id,usuario_id,agente)
           VALUES (%s,%s,%s,'aprobacion_prueba') RETURNING id""",
        (empresa, proyecto["id"], user["id"]),
    ).fetchone()["id"]
    run = db.execute(
        "INSERT INTO agent_runs(empresa_id,conversacion_id,modelo,estado) VALUES (%s,%s,'falso','en_curso') RETURNING id",
        (empresa, conv),
    ).fetchone()["id"]
    db.commit()

    class Argumentos(BaseModel):
        codigo: str = Field(min_length=1, max_length=40)
        nombre: str = Field(min_length=1, max_length=100)

    def registrar(db, actor, _proyecto, argumentos):
        db.execute(
            "INSERT INTO materiales(empresa_id,codigo,nombre,unidad,tipo) VALUES (%s,%s,%s,'kg','material')",
            (actor["empresa_id"], argumentos.codigo, argumentos.nombre),
        )
        return "Material registrado."

    def puede(db, actor, _proyecto):
        return puede_gestionar_precios(actor, db)

    class ModeloConPool(ModeloFalso):
        async def get_response(self, *args, **kwargs):
            with ExitStack() as pila:
                conexiones = [pila.enter_context(pool().connection(timeout=4)) for _ in range(pool().max_size)]
                assert conexiones[0].execute(
                    "SELECT estado FROM agent_runs WHERE empresa_id=%s AND id=%s", (empresa, run),
                ).fetchone() == {"estado": "en_curso"}
            consultas.append(True)
            return await super().get_response(*args, **kwargs)

    herramienta = aprobaciones.Escritura(
        nombre="registrar_material_prueba", descripcion="Dar de alta un material", argumentos=Argumentos,
        permiso=puede, ejecutar=registrar,
    )

    @asynccontextmanager
    async def abrir(_modelo, tools):
        modelo = ModeloConPool(
            herramienta.nombre, {"codigo": "APROBACION-01", "nombre": "Material propuesto"},
            responder=lambda resultado: f"Resultado: {resultado}",
        )
        yield Agent(name="Prueba de aprobación", model=modelo, tools=tools)

    configuracion = aprobaciones.AgenteRegistrado(abrir=abrir, escrituras=(herramienta,))
    monkeypatch.setitem(aprobaciones.AGENTES, "aprobacion_prueba", configuracion)
    contexto = aprobaciones.Contexto(user, proyecto, run, conv)
    payload = asyncio.run(aprobaciones.iniciar(
        "aprobacion_prueba", "falso", contexto, [{"role": "user", "content": "Proponé un material"}],
    ))
    return {"payload": payload, "run": run, "usuario": user, "consultas": consultas}


def _ruta(turno, accion):
    dato, = turno["payload"]["aprobaciones"]
    return f"/agentes/runs/{turno['run']}/tool-calls/{dato['id']}/{accion}"


def _efectos(db, turno):
    return db.execute(
        "SELECT count(*) AS n FROM materiales WHERE empresa_id=%s AND codigo='APROBACION-01'",
        (turno["usuario"]["empresa_id"],),
    ).fetchone()["n"]


def _estado(db, turno):
    return db.execute("SELECT estado FROM agent_runs WHERE id=%s", (turno["run"],)).fetchone()["estado"]


def test_espera_y_aprueba_una_vez_sin_retener_el_pool(db, turno, como):
    assert _estado(db, turno) == "esperando_aprobacion"
    assert _efectos(db, turno) == 0
    pendiente, = turno["payload"]["aprobaciones"]
    assert pendiente["argumentos"] == {"codigo": "APROBACION-01", "nombre": "Material propuesto"}
    assert db.execute(
        "SELECT estado,argumentos FROM tool_calls WHERE agent_run_id=%s", (turno["run"],),
    ).fetchone() == {"estado": "pendiente", "argumentos": pendiente["argumentos"]}
    user = turno["usuario"]
    cliente = como(user["email"])
    ruta = _ruta(turno, "aprobar")
    assert cliente.post(ruta, json={}).status_code == 403
    headers = {"X-CSRF": csrf_de(user)}
    r = cliente.post(ruta, json={}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["respuesta"] == "Resultado: Material registrado."
    assert _estado(db, turno) == "hecho" and _efectos(db, turno) == 1
    assert cliente.post(ruta, json={}, headers=headers).status_code == 409
    assert _efectos(db, turno) == 1 and len(turno["consultas"]) == 2
    assert db.execute("SELECT 1 FROM auditoria WHERE accion='agente.aprobacion'").fetchone()


def test_rechaza_y_entrega_el_motivo_al_modelo(db, turno, como):
    user = turno["usuario"]
    r = como(user["email"]).post(_ruta(turno, "rechazar"), json={}, headers={"X-CSRF": csrf_de(user)})
    assert r.status_code == 200, r.text
    assert f"rechazado por {user['nombre']}" in r.json()["respuesta"]
    assert _estado(db, turno) == "hecho" and _efectos(db, turno) == 0
    assert db.execute("SELECT 1 FROM auditoria WHERE accion='agente.rechazo'").fetchone()


def test_auth_y_aprobaciones_concurrentes(db, mundo, turno, como):
    ruta = _ruta(turno, "aprobar")
    user = turno["usuario"]
    for ajeno in (mundo["admin_a"], mundo["admin_b"]):
        assert como(ajeno["email"]).post(ruta, json={}, headers={"X-CSRF": csrf_de(ajeno)}).status_code == 404
    db.execute("DELETE FROM usuario_areas WHERE usuario_id=%s", (user["id"],))
    db.commit()
    cliente = como(user["email"])
    headers = {"X-CSRF": csrf_de(user)}
    assert cliente.post(ruta, json={}, headers=headers).status_code == 403
    assert _efectos(db, turno) == 0
    db.execute(
        """INSERT INTO usuario_areas(usuario_id,area_id) SELECT %s,id FROM areas
            WHERE empresa_id=%s AND codigo='gestion_administrativa'""", (user["id"], user["empresa_id"]),
    )
    db.commit()
    otro = como(user["email"])
    barrera = Barrier(2)

    def postear(cliente):
        barrera.wait(timeout=4)
        return cliente.post(ruta, json={}, headers=headers).status_code

    with ThreadPoolExecutor(2) as executor:
        assert sorted(executor.map(postear, (cliente, otro))) == [200, 409]
    assert _efectos(db, turno) == 1
