"""Matriz de permisos y aislamiento entre empresas y proyectos (M0)."""
from tests.conftest import csrf_de


def codigos_visibles(html: str, *proyectos) -> set[str]:
    return {p["codigo"] for p in proyectos if f"/proyecto/{p['codigo']}" in html}


def test_admin_ve_todo_lo_de_su_empresa_y_nada_de_otra(mundo, como):
    c = como("admin@a.test")
    html = c.get("/tipo/revit").text
    assert codigos_visibles(html, mundo["p1"], mundo["p2"]) == {mundo["p1"]["codigo"], mundo["p2"]["codigo"]}
    # El proyecto de la empresa B tiene el MISMO código (PR-año-001) pero no se ve: el nombre lo delata.
    assert "Proyecto de B" not in html


def test_miembro_ve_solo_donde_esta_asignado(mundo, como):
    c = como("ana@a.test")
    assert c.get(f"/proyecto/{mundo['p1']['codigo']}").status_code == 200
    assert c.get(f"/proyecto/{mundo['p2']['codigo']}").status_code == 404
    html = c.get("/").text
    assert "Casa con cliente" in html and "Local sin Ana" not in html


def test_cliente_ve_solo_los_proyectos_de_su_cliente(mundo, como):
    c = como("cliente@a.test")
    assert c.get(f"/proyecto/{mundo['p1']['codigo']}").status_code == 200
    assert c.get(f"/proyecto/{mundo['p2']['codigo']}").status_code == 404
    # Sin actividad interna ni panel admin.
    assert "Actividad reciente" not in c.get(f"/proyecto/{mundo['p1']['codigo']}").text
    assert c.get("/admin").status_code == 403


def test_nadie_ve_proyectos_de_otra_empresa_por_url(mundo, como):
    """El código PR-AAAA-001 existe en las dos empresas: cada uno ve el SUYO."""
    assert mundo["p1"]["codigo"] == mundo["pb"]["codigo"]
    html_a = como("admin@a.test").get(f"/proyecto/{mundo['pb']['codigo']}").text
    assert "Proyecto de B" not in html_a and "Casa con cliente" in html_a
    html_b = como("admin@b.test").get(f"/proyecto/{mundo['pb']['codigo']}").text
    assert "Proyecto de B" in html_b and "Casa con cliente" not in html_b


def test_colaborador_no_edita_y_director_si(mundo, como):
    p1, p2 = mundo["p1"], mundo["p2"]
    ana = como("ana@a.test")
    r = ana.post(f"/proyecto/{p1['codigo']}/editar",
                 data={"csrf": csrf_de(mundo["ana"]), "nombre": "Hackeado", "etapa": "proyecto",
                       "estado": "activo", "avance": 10})
    assert r.status_code == 403
    beto = como("beto@a.test")
    r = beto.post(f"/proyecto/{p2['codigo']}/editar",
                  data={"csrf": csrf_de(mundo["beto"]), "nombre": "Local renovado", "etapa": "proyecto",
                        "estado": "activo", "avance": 25})
    assert r.status_code == 303
    assert "Local renovado" in beto.get(f"/proyecto/{p2['codigo']}").text


def test_hitos_y_visibilidad_para_el_cliente(mundo, como):
    """El director carga hitos; el cliente ve solo los marcados como visibles."""
    p1 = mundo["p1"]
    admin = como("admin@a.test")
    for titulo, visible in [("Entrega municipal", "1"), ("Reunión interna", "")]:
        r = admin.post(f"/proyecto/{p1['codigo']}/hitos",
                       data={"csrf": csrf_de(mundo["admin_a"]), "titulo": titulo, "fecha": "2026-12-15",
                             "visible_cliente": visible})
        assert r.status_code == 303
    html = admin.get(f"/proyecto/{p1['codigo']}").text
    assert "15/12/2026" in html and "Reunión interna" in html
    html_cliente = como("cliente@a.test").get(f"/proyecto/{p1['codigo']}").text
    assert "Entrega municipal" in html_cliente and "Reunión interna" not in html_cliente


def test_director_no_puede_sumar_gente_de_otra_empresa(mundo, como):
    beto = como("beto@a.test")
    r = beto.post(f"/proyecto/{mundo['p2']['codigo']}/equipo",
                  data={"csrf": csrf_de(mundo["beto"]), "usuario_id": mundo["admin_b"]["id"], "rol": "lector"})
    assert r.status_code == 400


def test_admin_no_toca_usuarios_de_otra_empresa(mundo, como):
    a = como("admin@a.test")
    r = a.post(f"/admin/usuarios/{mundo['admin_b']['id']}/acceso", data={"csrf": csrf_de(mundo["admin_a"])})
    assert r.status_code == 404


def test_miembro_no_entra_al_panel_admin(mundo, como):
    assert como("ana@a.test").get("/admin/usuarios").status_code == 403


def test_post_sin_csrf_se_rechaza(mundo, como):
    beto = como("beto@a.test")
    r = beto.post(f"/proyecto/{mundo['p2']['codigo']}/editar",
                  data={"nombre": "x", "etapa": "proyecto", "estado": "activo", "avance": 1})
    assert r.status_code == 403
    # Tampoco sirve el CSRF de otra persona.
    r = beto.post(f"/proyecto/{mundo['p2']['codigo']}/editar",
                  data={"csrf": csrf_de(mundo["ana"]), "nombre": "x", "etapa": "proyecto", "estado": "activo",
                        "avance": 1})
    assert r.status_code == 403


def test_usuario_desactivado_pierde_la_sesion(mundo, como, db):
    ana = como("ana@a.test")
    assert ana.get("/").status_code == 200
    db.execute("UPDATE usuarios SET activo = false WHERE id = %s", (mundo["ana"]["id"],))
    db.commit()
    r = ana.get("/")
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_sin_sesion_redirige_al_login(app_client, mundo):
    r = app_client().get(f"/proyecto/{mundo['p1']['codigo']}")
    assert r.status_code == 303 and r.headers["location"] == "/login"
