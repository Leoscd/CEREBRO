"""Compara cada biblioteca vendorizada con su distribución fijada."""

import base64
import hashlib
import io
import json
import re
import sys
import tarfile
import urllib.request
from pathlib import Path, PurePosixPath, PureWindowsPath


DIRECTORIO_VENDOR = Path(__file__).resolve().parents[1] / "app/static/vendor"
MANIFIESTO = "ORIGEN.json"
LICENCIA_WEB_IFC = {
    "url": "https://raw.githubusercontent.com/ThatOpen/engine_web-ifc/d7225478eb552ecc052bbad2f4ecf3a835d535fd/LICENSE.md",
    "sha256": "1f256ecad192880510e84ad60474eab7589218784b9a50bc7ceee34c2b91f1d5",
}


class _SinRedirecciones(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def descargar_tarball(url: str) -> bytes:
    cliente = urllib.request.build_opener(_SinRedirecciones())
    with cliente.open(url, timeout=30) as respuesta:
        return respuesta.read()


def _archivos_locales(directorio: Path) -> dict[str, Path]:
    archivos = {}
    for ruta in directorio.rglob("*"):
        nombre = ruta.relative_to(directorio).as_posix()
        if ruta.is_symlink() or ruta.is_junction():
            raise ValueError(f"Enlace inesperado en el directorio local: {nombre}")
        if ruta.is_file() and nombre != MANIFIESTO:
            archivos[nombre] = ruta
    return archivos


def _hashes_publicados(tarball: bytes, rutas: set[str]) -> dict[str, str]:
    hashes = {}
    with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as paquete:
        for miembro in paquete:
            nombre = miembro.name
            ruta = PurePosixPath(nombre)
            if ruta.is_absolute() or ".." in ruta.parts or "\\" in nombre or PureWindowsPath(nombre).drive:
                raise ValueError(f"Ruta insegura en el tarball: {nombre}")
            if nombre not in rutas:
                continue
            if not miembro.isfile() or nombre in hashes:
                raise ValueError(f"Esperaba un único archivo regular en el tarball: {nombre}")
            with paquete.extractfile(miembro) as archivo:
                hashes[nombre] = hashlib.file_digest(archivo, "sha256").hexdigest()
    return hashes


def verificar(directorio: Path) -> None:
    origen = json.loads((directorio / MANIFIESTO).read_text(encoding="utf-8"))
    mapa = origen["archivos"]
    if not isinstance(mapa, dict) or not mapa or not all(isinstance(ruta, str) for ruta in mapa.values()):
        raise ValueError("ORIGEN.json debe declarar un mapa de archivos con rutas en el tarball.")

    paquete = origen["paquete"]
    version = origen["version"]
    nombre_npm = r"[a-z0-9][a-z0-9._-]*"
    if not re.fullmatch(rf"(?:@{nombre_npm}/)?{nombre_npm}", paquete) or not re.fullmatch(r"[0-9][0-9A-Za-z.+-]*", version):
        raise ValueError("Paquete o versión de npm inválidos.")
    url_esperada = f"https://registry.npmjs.org/{paquete}/-/{paquete.split('/')[-1]}-{version}.tgz"
    if origen["url"] != url_esperada:
        raise ValueError("ORIGEN.json debe apuntar al tarball exacto en registry.npmjs.org.")

    declarados = set(mapa)
    licencia_externa = (paquete, version) == ("web-ifc", "0.0.68")
    if licencia_externa:
        if origen.get("licencia_externa") != LICENCIA_WEB_IFC or "LICENSE" in mapa:
            raise ValueError("Falta la procedencia fijada de LICENSE de web-ifc.")
        declarados.add("LICENSE")
    elif "licencia_externa" in origen:
        raise ValueError("Licencia externa no autorizada para este paquete.")
    archivos = _archivos_locales(directorio)
    sin_declarar = archivos.keys() - declarados
    if sin_declarar:
        raise ValueError("Sin declarar en ORIGEN.json: " + ", ".join(sorted(sin_declarar)))
    faltantes = declarados - archivos.keys()
    if faltantes:
        raise ValueError("Faltan archivos declarados en ORIGEN.json: " + ", ".join(sorted(faltantes)))

    if licencia_externa and hashlib.sha256(archivos["LICENSE"].read_bytes()).hexdigest() != LICENCIA_WEB_IFC["sha256"]:
        raise ValueError("LICENSE de web-ifc difiere del SHA-256 oficial fijado.")
    tarball = descargar_tarball(url_esperada)
    firma = base64.b64encode(hashlib.sha512(tarball).digest()).decode("ascii")
    if f"sha512-{firma}" != origen["integrity"]:
        raise ValueError(f"SHA-512 esperado para {url_esperada}: {origen['integrity']}; se obtuvo sha512-{firma}")

    hashes = _hashes_publicados(tarball, set(mapa.values()))
    for nombre, ruta_npm in mapa.items():
        esperado = hashes.get(ruta_npm)
        if esperado is None:
            raise ValueError(f"{nombre}: faltó el archivo {ruta_npm} en el tarball de npm.")
        with archivos[nombre].open("rb") as archivo:
            calculado = hashlib.file_digest(archivo, "sha256").hexdigest()
        if calculado != esperado:
            raise ValueError(f"{nombre}: SHA-256 esperado de {ruta_npm}: {esperado}; se obtuvo {calculado}")


def main(directorio: Path | None = None) -> int:
    try:
        directorios = [directorio] if directorio is not None else sorted(p for p in DIRECTORIO_VENDOR.iterdir() if p.is_dir())
        for local in directorios:
            if local.is_symlink() or local.is_junction():
                raise ValueError(f"Directorio de vendor inesperado: {local}")
            verificar(local)
    except (OSError, EOFError, KeyError, TypeError, ValueError, tarfile.TarError) as error:
        print(f"Integridad de vendor: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
