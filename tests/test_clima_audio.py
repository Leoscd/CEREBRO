import httpx

from app import config
from app.services import clima, transcripcion
from app.worker import procesar_uno
from tests.conftest import csrf_de

MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x64" + bytes(420)


def _parte(db, mundo, como, *, ubicacion=False):
    proyecto, actor = mundo["p1"], mundo["admin_a"]
    cliente = como(actor["email"])
    ruta = f"/proyecto/{proyecto['codigo']}"
    csrf = {"csrf": csrf_de(actor)}
    if ubicacion:
        r = cliente.post(f"{ruta}/ubicacion", data=csrf | {"lat": "-26,8241", "lon": "-65,2226"})
        assert r.status_code == 303, r.text
    r = cliente.post(f"{ruta}/obra/partes/hoy", data=csrf)
    assert r.status_code == 303
    return cliente, r.headers["location"], csrf


def _trabajar(db):
    for _ in range(8):
        if not procesar_uno(db):
            return


def test_clima_usa_ubicacion_y_fecha_del_parte(db, mundo, como, monkeypatch):
    dias = []

    def api(url, *, params, timeout):
        assert url == "https://api.open-meteo.com/v1/forecast"
        assert params["latitude"] == "-26.824100" and timeout <= 5
        assert params["start_date"] == params["end_date"]
        dias.append(params["start_date"])
        return httpx.Response(200, request=httpx.Request("GET", url), json={"daily": {
            "time": [dias[0]], "weather_code": [63], "temperature_2m_min": [18],
            "temperature_2m_max": [28], "precipitation_sum": [4.2],
        }})

    monkeypatch.setattr(clima.httpx, "get", api)
    cliente, parte, _ = _parte(db, mundo, como, ubicacion=True)
    _trabajar(db)
    assert "Lluvia" in cliente.get(parte).text
    datos = db.execute("SELECT fecha,datos FROM reportes_obra").fetchone()
    assert dias == [datos["fecha"].isoformat()]
    assert datos["datos"]["condiciones"]["propuesto"]["codigo"] == 63


def test_clima_sin_ubicacion_o_red_no_impide_confirmar(db, mundo, como, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ALMACEN_DIR", tmp_path)
    llamadas = []

    def sin_red(*args, **kwargs):
        llamadas.append(1)
        raise httpx.ConnectError("sin red")

    monkeypatch.setattr(clima.httpx, "get", sin_red)
    cliente, parte, csrf = _parte(db, mundo, como)
    _trabajar(db)
    assert llamadas == []
    assert "Sin datos" in cliente.get(parte).text
    db.execute("UPDATE proyectos SET lat=-26,lon=-65 WHERE id=%s", (mundo["p1"]["id"],))
    db.execute("UPDATE jobs SET estado='pendiente' WHERE tipo='parte.clima'")
    db.commit()
    _trabajar(db)
    assert llamadas == [1]
    assert "Sin datos" in cliente.get(parte).text
    for seccion, campos in (
        ("condiciones", {"confirmado": "1"}), ("jornada", {"tipo": "no_laborable"}), ("hys", {"epp_ok": "1"}),
    ):
        assert cliente.post(f"{parte}/secciones/{seccion}", data=csrf | campos).status_code == 303
    assert cliente.post(f"{parte}/confirmar", data=csrf).status_code == 303


def test_audio_falso_se_revisa_antes_de_entrar_al_parte(db, mundo, como, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ALMACEN_DIR", tmp_path)
    monkeypatch.setattr(config, "TRANSCRIPCION_PROVEEDOR", "falso")
    cliente, parte, csrf = _parte(db, mundo, como)
    url = f"{parte}/audios"
    assert cliente.post(url, data=csrf, files={"audio": ("falso.m4a", b"mentira")}).status_code == 400
    assert cliente.post(url, data=csrf, files={"audio": ("enorme.mp3", MP3 + bytes(20 * 1024**2))}).status_code == 413
    assert cliente.post(url, data=csrf, files={"audio": ("voz.mp3", MP3)}).status_code == 303
    _trabajar(db)
    propuesta = db.execute("SELECT * FROM audios_parte").fetchone()
    assert propuesta["texto"] and propuesta["texto"] in cliente.get(parte).text
    assert db.execute("SELECT datos->>'resumen' AS resumen FROM reportes_obra").fetchone()["resumen"] == ""
    datos = csrf | {"texto": "Dictado corregido con té y cañerías."}
    accion = f"{url}/{propuesta['id']}/aceptar"
    assert cliente.post(accion, data=datos).status_code == 303
    assert cliente.post(accion, data=datos).status_code == 409
    assert db.execute("SELECT datos->>'resumen' AS resumen FROM reportes_obra").fetchone()["resumen"] == datos["texto"]
    monkeypatch.setattr(config, "TRANSCRIPCION_PROVEEDOR", "openai")
    monkeypatch.setattr(config, "MODELO_TRANSCRIPCION", "")
    respuesta = cliente.post(url, data=csrf, files={"audio": ("voz.mp3", MP3)})
    assert respuesta.status_code == 503 and "MODELO_TRANSCRIPCION" in respuesta.text


def test_firmas_de_audio():
    assert transcripcion._formato(b"\x00\x00\x00\x14ftypM4A " + bytes(8)) == "m4a"
    assert transcripcion._formato(b"OggS\x00" + bytes(22) + b"OpusHead") == "ogg"
    assert transcripcion._formato(b"\x1a\x45\xdf\xa3" + b"webm" + bytes(20) + b"A_OPUS") == "webm"
    assert transcripcion._formato(MP3) == "mp3"
    assert transcripcion._formato(b"\x00\x00\x00\x14ftypmp42" + bytes(8) + b"hdlr" + bytes(8) + b"vide") is None
