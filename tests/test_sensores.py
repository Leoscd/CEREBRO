"""Los sensores del harness tienen que detectar lo que dicen detectar (y callarse si está bien).

Sin base de datos: corren en milisegundos. Cada caso nuevo de harness/log.md que se
convierte en sensor suma acá su prueba de regresión.
"""
from scripts.checks import fast, protegidos


def test_repo_actual_pasa_silencioso():
    assert [str(f) for f in fast.correr()] == []


def test_migracion_sellada_editada(tmp_path, monkeypatch):
    m = tmp_path / "0001_base.sql"
    m.write_text("CREATE TABLE a (id int);\n", encoding="utf-8")
    lock = tmp_path / "migraciones.lock"
    lock.write_text(f"0001_base.sql {fast._sha(m)}\n", encoding="utf-8")
    monkeypatch.setattr(fast, "MIGRACIONES", tmp_path)
    monkeypatch.setattr(fast, "LOCK_MIGRACIONES", lock)
    monkeypatch.setattr(fast, "RAIZ", tmp_path)
    assert fast.sensor_migraciones() == []
    m.write_text("CREATE TABLE a (id bigint);\n", encoding="utf-8")
    assert [f.regla for f in fast.sensor_migraciones()] == ["migracion-sellada"]


def test_migracion_con_salto_de_numero(tmp_path, monkeypatch):
    (tmp_path / "0001_base.sql").write_text("", encoding="utf-8")
    (tmp_path / "0003_otra.sql").write_text("", encoding="utf-8")
    monkeypatch.setattr(fast, "MIGRACIONES", tmp_path)
    monkeypatch.setattr(fast, "LOCK_MIGRACIONES", tmp_path / "no-existe.lock")
    monkeypatch.setattr(fast, "RAIZ", tmp_path)
    assert [f.regla for f in fast.sensor_migraciones()] == ["migracion-numero"]


def test_dinero_y_fechas(tmp_path, monkeypatch):
    (tmp_path / "0001_base.sql").write_text(
        "CREATE TABLE p (\n  monto numeric(12,2),\n  total_centavos bigint,\n"
        "  creado timestamp,\n  vence timestamptz\n);\n", encoding="utf-8")
    monkeypatch.setattr(fast, "MIGRACIONES", tmp_path)
    monkeypatch.setattr(fast, "RAIZ", tmp_path)
    assert sorted(f.regla for f in fast.sensor_sql_dominio()) == ["dinero", "fecha"]


def test_modelo_fijo_y_otro_proveedor(tmp_path, monkeypatch):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "agente.py").write_text(
        'import anthropic\nMODELO = "gpt-4.1-mini"\nOK = config.MODELO_DOCUMENTADOR\n', encoding="utf-8")
    monkeypatch.setattr(fast, "RAIZ", tmp_path)
    assert sorted(f.regla for f in fast.sensor_ia()) == ["modelo-fijo", "solo-openai"]


def test_rutas_csrf_y_empresa_id(tmp_path, monkeypatch):
    (tmp_path / "app" / "routers").mkdir(parents=True)
    (tmp_path / "app" / "routers" / "x.py").write_text(
        "from app.security import check_csrf, require_user\n\n"
        "def _admin(user=Depends(check_csrf)):\n    return user\n\n"
        "@router.post('/a')\ndef bien(user=Depends(_admin)):\n    pass\n\n"
        "@router.post('/b')\ndef sin_csrf(user=Depends(require_user)):\n    pass\n\n"
        "@router.get('/c')\ndef ajena(empresa_id: int, user=Depends(require_user)):\n    pass\n",
        encoding="utf-8")
    monkeypatch.setattr(fast, "RAIZ", tmp_path)
    monkeypatch.setattr(fast, "POST_SIN_CSRF", tmp_path / "no-existe.txt")
    assert sorted(f.regla for f in fast.sensor_rutas()) == ["aislamiento", "csrf"]


def test_csrf_no_se_engana_con_el_nombre(tmp_path, monkeypatch):
    # H-008: una función local llamada check_csrf que no valida nada no cuenta como CSRF.
    (tmp_path / "app" / "routers").mkdir(parents=True)
    (tmp_path / "app" / "routers" / "y.py").write_text(
        "from app import security\n\n"
        "def check_csrf(user=Depends(require_user)):\n    return user\n\n"
        "async def _envoltorio(request, user=Depends(require_user)):\n"
        "    return await security.check_csrf(request, user)\n\n"
        "@router.post('/falsa')\ndef falsa(user=Depends(check_csrf)):\n    pass\n\n"
        "@router.post('/buena')\ndef buena(user=Depends(_envoltorio)):\n    pass\n",
        encoding="utf-8")
    monkeypatch.setattr(fast, "RAIZ", tmp_path)
    monkeypatch.setattr(fast, "POST_SIN_CSRF", tmp_path / "no-existe.txt")
    assert [f.donde.split()[-1] for f in fast.sensor_rutas()] == ["falsa"]


def test_form_opcional_tipado(tmp_path, monkeypatch):
    # H-013: un <select> con opción vacía manda "" y `int | None = Form(None)` responde 422.
    (tmp_path / "app" / "routers").mkdir(parents=True)
    (tmp_path / "app" / "routers" / "z.py").write_text(
        "from app.security import check_csrf\n\n"
        "@router.post('/a')\ndef a(x: int | None = Form(None), y: Optional[date] = Form(None),\n"
        "      z: str | None = Form(None), w: str = Form(''), user=Depends(check_csrf)):\n    pass\n",
        encoding="utf-8")
    monkeypatch.setattr(fast, "RAIZ", tmp_path)
    monkeypatch.setattr(fast, "POST_SIN_CSRF", tmp_path / "no-existe.txt")
    assert sorted(f.donde.split("(")[-1].rstrip(")") for f in fast.sensor_rutas()) == ["x", "y"]


def test_protegidos():
    assert protegidos.violaciones(["app/main.py", "harness/tareas/T-001.md", "harness/candidatos/C-001.md"]) == []
    assert protegidos.violaciones(["AGENTS.md", "scripts/checks/fast.py", ".agents/skills/x/SKILL.md", "harness/lotes/L-001.md"]) == [
        "AGENTS.md", "scripts/checks/fast.py", ".agents/skills/x/SKILL.md", "harness/lotes/L-001.md"]


def _guardia(cmd):
    import json
    import subprocess
    import sys
    from pathlib import Path
    hook = Path(__file__).resolve().parents[1] / "scripts" / "hooks" / "guardia.py"
    evento = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
    salida = subprocess.run([sys.executable, str(hook)], input=evento, capture_output=True, text=True).stdout
    return json.loads(salida)["hookSpecificOutput"]["permissionDecision"] if salida.strip() else None


def test_guardia_distingue_borrado_seguro_de_forzado():
    # H-005: el patrón ignoraba mayúsculas y bloqueaba también el borrado seguro.
    assert _guardia("git branch -d rama-mergeada") is None
    assert _guardia("git branch " + "-D rama") == "deny"
    assert _guardia("git push " + "--force origin x") == "deny"
    assert _guardia("gh pr merge 3") == "ask"


def test_rutas_tocar_multilinea():
    # H-006: la lista "Tocar" de una tarea puede seguir en el renglón siguiente.
    from scripts.harness import rutas_tocar
    texto = ("## Alcance\n- Tocar: `app/a.py`, `app/b.py` (solo `ficha`),\n  `tests/test_c.py`.\n"
             "- No tocar: `app/permisos.py`.\n")
    assert rutas_tocar(texto) == ["app/a.py", "app/b.py", "tests/test_c.py"]
