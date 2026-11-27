import base64
import hashlib
import io
import json
import tarfile

import pytest

from scripts import verificar_vendor


@pytest.fixture
def vendor(tmp_path, monkeypatch):
    def preparar(*, contenido_local=b"original\n", extra=False, miembro_extra=None, integrity=None):
        miembros = {"package/build/pdf.mjs": b"original\n"}
        if miembro_extra is not None:
            miembros[miembro_extra] = b"extra\n"
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archivo:
            for nombre, contenido in miembros.items():
                miembro = tarfile.TarInfo(nombre)
                miembro.size = len(contenido)
                archivo.addfile(miembro, io.BytesIO(contenido))
        tarball = buffer.getvalue()
        firma = base64.b64encode(hashlib.sha512(tarball).digest()).decode("ascii")
        origen = {
            "paquete": "pdfjs-dist",
            "version": "6.5.438",
            "url": "https://registry.npmjs.org/pdfjs-dist/-/pdfjs-dist-6.5.438.tgz",
            "integrity": integrity or f"sha512-{firma}",
            "archivos": {"pdf.mjs": "package/build/pdf.mjs"},
        }
        (tmp_path / "ORIGEN.json").write_text(json.dumps(origen), encoding="utf-8")
        if contenido_local is not None:
            (tmp_path / "pdf.mjs").write_bytes(contenido_local)
        if extra:
            (tmp_path / "extra.mjs").write_bytes(b"extra\n")
        monkeypatch.setattr(verificar_vendor, "descargar_tarball", lambda url: tarball)
        return tmp_path

    return preparar


def test_vendor_identico_es_silencioso(vendor, capsys):
    assert verificar_vendor.main(vendor()) == 0
    assert capsys.readouterr() == ("", "")


def test_vendor_detecta_archivo_modificado(vendor, capsys):
    assert verificar_vendor.main(vendor(contenido_local=b"modificado\n")) == 1
    mensaje = capsys.readouterr().err
    assert "pdf.mjs" in mensaje
    assert "SHA-256 esperado" in mensaje


def test_vendor_detecta_archivo_no_declarado(vendor):
    with pytest.raises(ValueError, match=r"Sin declarar en ORIGEN\.json: extra\.mjs"):
        verificar_vendor.verificar(vendor(extra=True))


def test_vendor_detecta_archivo_faltante(vendor):
    with pytest.raises(ValueError, match=r"Faltan archivos declarados en ORIGEN\.json: pdf\.mjs"):
        verificar_vendor.verificar(vendor(contenido_local=None))


def test_vendor_detecta_integrity_distinto(vendor):
    with pytest.raises(ValueError, match="SHA-512 esperado"):
        verificar_vendor.verificar(vendor(integrity="sha512-incorrecto"))


@pytest.mark.parametrize("ruta", ["package/../extra.mjs", "/extra.mjs", "C:/extra.mjs"])
def test_vendor_rechaza_ruta_insegura_aunque_no_este_en_el_mapa(vendor, ruta):
    with pytest.raises(ValueError, match="Ruta insegura"):
        verificar_vendor.verificar(vendor(miembro_extra=ruta))


def test_vendor_rechaza_otro_host(vendor):
    directorio = vendor()
    ruta = directorio / "ORIGEN.json"
    ruta.write_text(ruta.read_text().replace("registry.npmjs.org", "example.org"))
    with pytest.raises(ValueError, match="registry.npmjs.org"):
        verificar_vendor.verificar(directorio)


def test_vendor_detecta_un_byte_de_o3dv(vendor):
    directorio = vendor()
    ruta = directorio / "ORIGEN.json"
    origen = json.loads(ruta.read_text().replace("pdfjs-dist", "online-3d-viewer"))
    origen["archivos"] = {"o3dv.min.js": origen["archivos"].pop("pdf.mjs")}
    ruta.write_text(json.dumps(origen))
    motor = directorio / "o3dv.min.js"
    (directorio / "pdf.mjs").rename(motor)
    verificar_vendor.verificar(directorio)
    motor.write_bytes(b"Original\n")
    with pytest.raises(ValueError, match=r"o3dv.min.js: SHA-256"):
        verificar_vendor.verificar(directorio)


def test_vendor_rechaza_licencia_ifc_alterada(tmp_path):
    publicado = verificar_vendor.DIRECTORIO_VENDOR / "web-ifc"
    manifiesto = json.loads((publicado / "ORIGEN.json").read_text())
    (tmp_path / "ORIGEN.json").write_text(json.dumps(manifiesto))
    for nombre in manifiesto["archivos"]:
        (tmp_path / nombre).touch()
    (tmp_path / "LICENSE").write_bytes(b"distinta")
    with pytest.raises(ValueError, match="LICENSE de web-ifc difiere"):
        verificar_vendor.verificar(tmp_path)
