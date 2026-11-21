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
        "def _admin(user=Depends(check_csrf)):\n    return user\n\n"
        "@router.post('/a')\ndef bien(user=Depends(_admin)):\n    pass\n\n"
        "@router.post('/b')\ndef sin_csrf(user=Depends(require_user)):\n    pass\n\n"
        "@router.get('/c')\ndef ajena(empresa_id: int, user=Depends(require_user)):\n    pass\n",
        encoding="utf-8")
    monkeypatch.setattr(fast, "RAIZ", tmp_path)
    monkeypatch.setattr(fast, "POST_SIN_CSRF", tmp_path / "no-existe.txt")
    assert sorted(f.regla for f in fast.sensor_rutas()) == ["aislamiento", "csrf"]


def test_protegidos():
    assert protegidos.violaciones(["app/main.py", "harness/tareas/T-001.md", "harness/candidatos/C-001.md"]) == []
    assert protegidos.violaciones(["AGENTS.md", "scripts/checks/fast.py", ".agents/skills/x/SKILL.md"]) == [
        "AGENTS.md", "scripts/checks/fast.py", ".agents/skills/x/SKILL.md"]
