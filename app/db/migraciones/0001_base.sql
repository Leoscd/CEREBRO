-- M0 · Fundaciones: empresas, usuarios, áreas, clientes, tipos de proyecto, proyectos,
-- equipo y auditoría inmutable. Toda tabla de negocio lleva empresa_id.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE empresas (
    id          bigserial PRIMARY KEY,
    nombre      text NOT NULL,
    slug        text NOT NULL UNIQUE,
    cuit        text,
    config      jsonb NOT NULL DEFAULT '{}'::jsonb,
    creada_en   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE clientes (
    id          bigserial PRIMARY KEY,
    empresa_id  bigint NOT NULL REFERENCES empresas(id),
    nombre      text NOT NULL,
    cuit        text,
    email       text,
    telefono    text,
    notas       text,
    creado_en   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX clientes_empresa ON clientes (empresa_id);

CREATE TABLE usuarios (
    id              bigserial PRIMARY KEY,
    empresa_id      bigint NOT NULL REFERENCES empresas(id),
    email           text NOT NULL UNIQUE,
    password_hash   text NOT NULL,
    nombre          text NOT NULL DEFAULT '',
    -- admin: ve y administra todo en su empresa · miembro: ve los proyectos donde está
    -- asignado · cliente: ve sus proyectos y lo compartido con él.
    rol_empresa     text NOT NULL DEFAULT 'miembro'
                    CHECK (rol_empresa IN ('admin', 'miembro', 'cliente')),
    cliente_id      bigint REFERENCES clientes(id),
    telefono        text,
    activo          boolean NOT NULL DEFAULT true,
    totp_secret     text,
    -- Sube al cambiar la contraseña: invalida las sesiones abiertas en otros equipos.
    sesion_version  integer NOT NULL DEFAULT 1,
    creado_en       timestamptz NOT NULL DEFAULT now(),
    ultimo_ingreso  timestamptz,
    CHECK (rol_empresa <> 'cliente' OR cliente_id IS NOT NULL)
);
CREATE INDEX usuarios_empresa ON usuarios (empresa_id);

CREATE TABLE areas (
    id          bigserial PRIMARY KEY,
    empresa_id  bigint NOT NULL REFERENCES empresas(id),
    codigo      text NOT NULL,
    nombre      text NOT NULL,
    descripcion text NOT NULL DEFAULT '',
    orden       integer NOT NULL DEFAULT 0,
    UNIQUE (empresa_id, codigo)
);

CREATE TABLE usuario_areas (
    usuario_id  bigint NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    area_id     bigint NOT NULL REFERENCES areas(id) ON DELETE CASCADE,
    rol         text NOT NULL DEFAULT 'integrante' CHECK (rol IN ('responsable', 'integrante')),
    PRIMARY KEY (usuario_id, area_id)
);

CREATE TABLE invitaciones (
    id              bigserial PRIMARY KEY,
    empresa_id      bigint NOT NULL REFERENCES empresas(id),
    code_hash       text NOT NULL UNIQUE,
    email           text NOT NULL,
    rol_empresa     text NOT NULL DEFAULT 'miembro'
                    CHECK (rol_empresa IN ('admin', 'miembro', 'cliente')),
    cliente_id      bigint REFERENCES clientes(id),
    proyecto_id     bigint,            -- FK más abajo (proyectos se crea después)
    rol_proyecto    text,
    creada_por      bigint REFERENCES usuarios(id),
    creada_en       timestamptz NOT NULL DEFAULT now(),
    expira_at       timestamptz NOT NULL,
    enviado_at      timestamptz,
    usada_por       bigint REFERENCES usuarios(id),
    usada_en        timestamptz,
    cancelada_en    timestamptz
);
CREATE INDEX invitaciones_empresa ON invitaciones (empresa_id);

CREATE TABLE password_resets (
    token_hash  text PRIMARY KEY,
    usuario_id  bigint NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    creado_en   timestamptz NOT NULL DEFAULT now(),
    expira_at   timestamptz NOT NULL,
    usado_at    timestamptz
);

-- Tipo de proyecto ≈ "curso" del RAG: agrupa proyectos y define el agente especializado.
CREATE TABLE tipos_proyecto (
    id                      bigserial PRIMARY KEY,
    empresa_id              bigint NOT NULL REFERENCES empresas(id),
    slug                    text NOT NULL,
    nombre                  text NOT NULL,
    descripcion             text NOT NULL DEFAULT '',
    icono                   text NOT NULL DEFAULT '',
    posicion                integer NOT NULL DEFAULT 0,
    publicado               boolean NOT NULL DEFAULT true,
    disciplina              text NOT NULL DEFAULT 'general'
                            CHECK (disciplina IN ('revit', 'autocad', 'sketchup', 'presupuestos', 'obra', 'general')),
    agente_slug             text NOT NULL DEFAULT 'documentador',
    agent_context           text NOT NULL DEFAULT '',
    herramientas_habilitadas jsonb NOT NULL DEFAULT '[]'::jsonb,
    plantilla_carpetas      jsonb NOT NULL DEFAULT '[]'::jsonb,
    UNIQUE (empresa_id, slug)
);

CREATE TABLE proyectos (
    id                  bigserial PRIMARY KEY,
    empresa_id          bigint NOT NULL REFERENCES empresas(id),
    tipo_proyecto_id    bigint NOT NULL REFERENCES tipos_proyecto(id),
    codigo              text NOT NULL,
    nombre              text NOT NULL,
    cliente_id          bigint REFERENCES clientes(id),
    descripcion         text NOT NULL DEFAULT '',
    direccion           text NOT NULL DEFAULT '',
    localidad           text NOT NULL DEFAULT '',
    lat                 double precision,
    lon                 double precision,
    superficie_m2       numeric(12, 2),
    etapa               text NOT NULL DEFAULT 'anteproyecto'
                        CHECK (etapa IN ('anteproyecto', 'proyecto', 'documentacion', 'licitacion', 'ejecucion', 'entrega')),
    estado              text NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo', 'pausado', 'finalizado')),
    avance              smallint NOT NULL DEFAULT 0 CHECK (avance BETWEEN 0 AND 100),
    fecha_inicio        date,
    fecha_fin_estimada  date,
    -- Sin autorización del cliente, nada del proyecto se usa para redes.
    permite_difusion    boolean NOT NULL DEFAULT false,
    carpeta_local       text NOT NULL DEFAULT '',
    revit_documento     text NOT NULL DEFAULT '',
    creado_por          bigint REFERENCES usuarios(id),
    creado_en           timestamptz NOT NULL DEFAULT now(),
    actualizado_en      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (empresa_id, codigo)
);
CREATE INDEX proyectos_empresa_tipo ON proyectos (empresa_id, tipo_proyecto_id);

ALTER TABLE invitaciones
    ADD CONSTRAINT invitaciones_proyecto_fk FOREIGN KEY (proyecto_id) REFERENCES proyectos(id) ON DELETE SET NULL;

CREATE TABLE proyecto_miembros (
    proyecto_id bigint NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
    usuario_id  bigint NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    -- director: administra el proyecto y su equipo · colaborador: trabaja y sube ·
    -- dt: dirección técnica (aprueba planos, partes de obra) · administracion: presupuestos
    -- y gastos · lector: solo mira.
    rol         text NOT NULL DEFAULT 'colaborador'
                CHECK (rol IN ('director', 'colaborador', 'dt', 'administracion', 'lector')),
    funcion     text NOT NULL DEFAULT '',
    desde       date NOT NULL DEFAULT current_date,
    PRIMARY KEY (proyecto_id, usuario_id)
);
CREATE INDEX proyecto_miembros_usuario ON proyecto_miembros (usuario_id);

CREATE TABLE hitos (
    id              bigserial PRIMARY KEY,
    empresa_id      bigint NOT NULL REFERENCES empresas(id),
    proyecto_id     bigint NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
    titulo          text NOT NULL,
    fecha           date NOT NULL,
    completado      boolean NOT NULL DEFAULT false,
    visible_cliente boolean NOT NULL DEFAULT true
);
CREATE INDEX hitos_proyecto ON hitos (proyecto_id, fecha);

-- Registro de actividad: solo se agregan filas. Ni la app ni un error pueden borrarlo.
CREATE TABLE auditoria (
    id          bigserial PRIMARY KEY,
    empresa_id  bigint NOT NULL,
    usuario_id  bigint,
    proyecto_id bigint,
    accion      text NOT NULL,
    objeto      text NOT NULL DEFAULT '',
    objeto_id   text NOT NULL DEFAULT '',
    detalle     jsonb NOT NULL DEFAULT '{}'::jsonb,
    ip          text NOT NULL DEFAULT '',
    creado_en   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX auditoria_empresa_fecha ON auditoria (empresa_id, creado_en DESC);
CREATE INDEX auditoria_proyecto ON auditoria (proyecto_id, creado_en DESC);

CREATE FUNCTION auditoria_inmutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'La auditoría no se modifica ni se borra';
END;
$$;
CREATE TRIGGER auditoria_sin_cambios BEFORE UPDATE OR DELETE ON auditoria
    FOR EACH ROW EXECUTE FUNCTION auditoria_inmutable();
CREATE TRIGGER auditoria_sin_truncate BEFORE TRUNCATE ON auditoria
    FOR EACH STATEMENT EXECUTE FUNCTION auditoria_inmutable();

-- Wrapper IMMUTABLE de unaccent para columnas generadas e índices de texto (M1).
-- Si la extensión no está (algunos Postgres embebidos de prueba), se usa translate().
DO $$
BEGIN
    BEGIN
        CREATE EXTENSION IF NOT EXISTS unaccent;
        EXECUTE $f$CREATE FUNCTION f_unaccent(text) RETURNS text
            LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
            AS $b$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $b$ $f$;
    EXCEPTION WHEN feature_not_supported OR undefined_file THEN
        EXECUTE $f$CREATE FUNCTION f_unaccent(text) RETURNS text
            LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
            AS $b$ SELECT translate($1, 'áéíóúüñÁÉÍÓÚÜÑàèìòùÀÈÌÒÙ', 'aeiouunAEIOUUNaeiouAEIOU') $b$ $f$;
    END;
END
$$;
