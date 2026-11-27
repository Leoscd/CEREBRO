import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import ifcopenshell
from ifcopenshell.api import aggregate, project, pset, root, spatial, unit

from app import config
from app.services import busqueda
from tests.conftest import csrf_de
from tests.test_busqueda import buscar, procesar_pendientes
from tests.test_subida import archivos_del_proyecto, primera_carpeta, subir
from tests.test_subida import directorio_almacen as directorio_almacen


def _modelo():
    modelo = project.create_file()
    obra = root.create_entity(modelo, ifc_class="IfcProject", name="Atrio crisoprasio")
    unidades = [unit.add_si_unit(modelo, unit_type=tipo, prefix="MILLI") for tipo in
                ("LENGTHUNIT", "AREAUNIT", "VOLUMEUNIT")]
    unit.assign_unit(modelo, units=unidades)
    edificio = root.create_entity(modelo, ifc_class="IfcBuilding", name="Pabellón")
    piso = root.create_entity(modelo, ifc_class="IfcBuildingStorey", name="Planta baja")
    piso.Elevation = 1200.0
    aggregate.assign_object(modelo, products=[edificio], relating_object=obra)
    aggregate.assign_object(modelo, products=[piso], relating_object=edificio)
    for area in (1250000.0, 2245000.0):
        muro = root.create_entity(modelo, ifc_class="IfcWall")
        spatial.assign_container(modelo, products=[muro], relating_structure=piso)
        qto = pset.add_qto(modelo, product=muro, name="Qto_WallBaseQuantities")
        pset.edit_qto(modelo, qto=qto, properties={"NetSideArea": area, "NetVolume": 500000000.0, "Length": 2200.0})
    puerta = root.create_entity(modelo, ifc_class="IfcDoor")
    spatial.assign_container(modelo, products=[puerta], relating_structure=piso)
    return modelo.to_string().encode("utf-8")


def _subir_ifc(db, mundo, como, contenido):
    p = mundo["p2"]
    assert subir(como("admin@a.test"), mundo["admin_a"], p, primera_carpeta(db, p),
                 "Modelo.ifc", contenido, "application/octet-stream").status_code == 303
    archivo, = archivos_del_proyecto(db, p)
    return f"/archivos/{archivo['id']}"


def test_separa_pisos_y_respeta_la_unidad_de_la_cantidad(tmp_path):
    from app.services import ifc

    modelo = ifcopenshell.file.from_string(_modelo().decode("utf-8"))
    piso_alto = root.create_entity(modelo, ifc_class="IfcBuildingStorey", name="Planta alta")
    origen = modelo.createIfcCartesianPoint((0.0, 0.0, 3500.0))
    piso_alto.ObjectPlacement = modelo.createIfcLocalPlacement(None, modelo.createIfcAxis2Placement3D(origen))
    muro = modelo.by_type("IfcWall")[1]
    spatial.assign_container(modelo, products=[muro], relating_structure=piso_alto)
    qto = muro.IsDefinedBy[0].RelatingPropertyDefinition
    area = next(q for q in qto.Quantities if q.Name == "NetSideArea")
    area.Unit = unit.add_si_unit(modelo, unit_type="AREAUNIT")
    area.AreaValue = 6.5
    ruta = tmp_path / "dos-pisos.ifc"
    modelo.write(ruta)
    resumen = ifc.resumen(ruta)
    superficies = {p["nombre"]: p["tipos"]["IfcWall"]["area_m2"] for p in resumen["pisos"]}
    assert superficies == {"Planta baja": 1.25, "Planta alta": 6.5}
    assert [p["elevacion_m"] for p in resumen["pisos"]] == [1.2, 3.5]
    assert resumen["tipos"]["IfcWall"]["area_m2"] == 7.75


def test_resumen_ifc_con_unidades_citas_y_aislamiento(db, mundo, como, directorio_almacen):
    ruta = _subir_ifc(db, mundo, como, _modelo())
    procesar_pendientes(db)
    d = db.execute("SELECT derivados FROM versiones_archivo").fetchone()["derivados"]
    resumen = d["meta"]["ifc"]
    assert d["vista_ifc"] == "lista" and resumen["esquema"] == "IFC4"
    assert resumen["proyecto"] == "Atrio crisoprasio" and resumen["edificios"] == ["Pabellón"]
    piso, = resumen["pisos"]
    assert piso["nombre"] == "Planta baja" and piso["elevacion_m"] == 1.2
    for tipos in [resumen["tipos"], piso["tipos"]]:
        assert tipos["IfcWall"] == {"cantidad": 2, "area_m2": 3.5, "volumen_m3": 1.0, "longitud_m": 4.4, "sin_cantidades": 0}
        assert tipos["IfcDoor"]["cantidad"] == tipos["IfcDoor"]["sin_cantidades"] == 1
        assert tipos["IfcDoor"]["area_m2"] is None
    textos = " ".join(r["texto"] for r in db.execute("SELECT texto FROM chunks ORDER BY orden"))
    assert "Planta baja" in textos and "2 muros" in textos and "3,50 m²" in textos
    admin = como("admin@a.test")
    pagina = admin.get(ruta)
    assert "Planta baja" in pagina.text and "Atrio crisoprasio" in pagina.text
    assert "<td>muros</td>" in pagina.text and "<td>puertas</td>" in pagina.text
    assert "IfcWall" not in pagina.text
    assert ruta + "#page=1" in buscar(admin, mundo["p2"], "crisoprasio").text
    for email, proyecto in [("ana@a.test", "p1"), ("admin@b.test", "pb")]:
        otro = como(email)
        assert otro.get(ruta).status_code == 404
        usuario = mundo["ana" if proyecto == "p1" else "admin_b"]
        assert busqueda.buscar(db, usuario, mundo["p2"], "crisoprasio") == []
        assert "Atrio crisoprasio" not in buscar(otro, mundo[proyecto], "crisoprasio").text

    # Un resumen generado por otra versión puede contener una clase aún sin traducir.
    db.execute("""UPDATE versiones_archivo SET derivados=jsonb_set(derivados, '{meta,ifc,pisos,0,tipos,IfcOtro}',
                  derivados #> '{meta,ifc,pisos,0,tipos,IfcWall}')""")
    db.commit()
    assert "<td>IfcOtro</td>" in admin.get(ruta).text


def test_descarta_el_resumen_si_cambia_la_version_durante_la_lectura(db, mundo, como, directorio_almacen, monkeypatch):
    from app.services import proceso_aislado

    original = _modelo()
    ruta = _subir_ifc(db, mundo, como, original)
    ejecutar = proceso_aislado.ejecutar

    def reemplazar_durante_la_lectura(*args, **kwargs):
        datos = ejecutar(*args, **kwargs)
        monkeypatch.setattr(proceso_aislado, "ejecutar", ejecutar)
        respuesta = como("admin@a.test").post(
            ruta + "/versiones", data={"csrf": csrf_de(mundo["admin_a"])},
            files={"archivo": ("Modelo.ifc", original.replace(b"crisoprasio", b"amatista"), "application/octet-stream")},
        )
        assert respuesta.status_code == 303
        return datos

    monkeypatch.setattr(proceso_aislado, "ejecutar", reemplazar_durante_la_lectura)
    procesar_pendientes(db)
    vieja, nueva = db.execute("SELECT id,derivados FROM versiones_archivo ORDER BY numero").fetchall()
    assert "ifc" not in vieja["derivados"]["meta"]
    assert nueva["derivados"]["meta"]["ifc"]["proyecto"] == "Atrio amatista"
    assert {r["version_id"] for r in db.execute("SELECT version_id FROM chunks")} == {nueva["id"]}


@pytest.mark.parametrize("contenido,limite", [(b"invalido", 200), (b"grande", 0)])
def test_ifc_invalido_o_grande(db, mundo, como, directorio_almacen, monkeypatch, contenido, limite):
    monkeypatch.setattr(config, "IFC_MAX_MB", limite, raising=False)
    ruta = _subir_ifc(db, mundo, como, contenido)
    procesar_pendientes(db)
    d = db.execute("SELECT derivados FROM versiones_archivo").fetchone()["derivados"]
    assert d.get("vista_ifc") == "error" and "ifc" not in d["meta"]
    assert "no está disponible" in como("admin@a.test").get(ruta).text
    assert db.execute("SELECT estado FROM jobs WHERE tipo='archivo.ifc'").fetchone()["estado"] == "hecho"


@pytest.mark.skipif(not shutil.which("docker"), reason="Compose se verifica en CI")
def test_configuracion_logs_onlyoffice(tmp_path):
    shutil.copyfile("docker-compose.yml", tmp_path / "docker-compose.yml")
    shutil.copyfile(".env.ci", tmp_path / ".env")
    salida = subprocess.check_output(["docker", "compose", "--profile", "onlyoffice", "config", "--format", "json"],
                                     cwd=tmp_path, text=True, timeout=30)
    servicio = json.loads(salida)["services"]["onlyoffice"]
    assert servicio["logging"] == {"driver": "json-file", "options": {"max-size": "10m", "max-file": "5"}}
    assert "no-new-privileges:true" in servicio["security_opt"]


@pytest.mark.parametrize(("dominio", "entorno", "perfiles"), [
    (False, "", ""),
    (True, 'ONLYOFFICE_URL=""', " --profile dominio"),
    (False, "ONLYOFFICE_URL=https://docs.test", " --profile onlyoffice"),
    (True, "ONLYOFFICE_URL='https://docs.test' # pruebas", " --profile dominio --profile onlyoffice"),
])
def test_perfiles_deploy(tmp_path, dominio, entorno, perfiles):
    bash = shutil.which("bash")
    if os.name == "nt" and (git := shutil.which("git")):
        git_bash = Path(git).parent.parent / "bin/bash.exe"
        if git_bash.is_file():
            bash = str(git_bash)
    if not bash:
        pytest.skip("El despliegue requiere Bash")
    (tmp_path / "scripts").mkdir()
    shutil.copyfile("scripts/deploy.sh", tmp_path / "scripts/deploy.sh")
    (tmp_path / ".env").write_text(f"SECRET_KEY=prueba\n{entorno}\n", encoding="utf-8")
    (tmp_path / "Caddyfile").write_text("proyectos.test" if dominio else "proyectos.tudominio.com")
    subprocess.run([bash, "-n", "scripts/deploy.sh"], cwd=tmp_path, check=True, timeout=20)
    dobles = 'docker() { echo "$*" >> llamadas; }; curl() { return 0; }; chown() { return 0; };'
    con_logs = dominio and "onlyoffice" in perfiles
    orden = " source scripts/deploy.sh" + (" --logs" if con_logs else "")
    proceso = subprocess.run([bash, "-c", dobles + orden], cwd=tmp_path, check=True,
                             capture_output=True, text=True, timeout=20)
    llamadas = (tmp_path / "llamadas").read_text().splitlines()
    assert f"compose{perfiles} up -d" in llamadas
    if con_logs:
        assert f"compose{perfiles} logs -f" in llamadas
    assert (perfiles.strip() or "sin perfiles opcionales") in proceso.stdout
