-- Carpetas, archivos y versiones de cada proyecto.
ALTER TABLE proyectos ADD UNIQUE (empresa_id, id);

CREATE TABLE carpetas (
    id          bigserial PRIMARY KEY,
    empresa_id  bigint NOT NULL,
    proyecto_id bigint NOT NULL,
    padre_id    bigint,
    nombre      text NOT NULL,
    posicion    integer NOT NULL DEFAULT 0,
    creada_en   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (empresa_id, proyecto_id, id),
    UNIQUE NULLS NOT DISTINCT (proyecto_id, padre_id, nombre),
    FOREIGN KEY (empresa_id, proyecto_id) REFERENCES proyectos(empresa_id, id),
    FOREIGN KEY (empresa_id, proyecto_id, padre_id) REFERENCES carpetas(empresa_id, proyecto_id, id)
);

CREATE TABLE archivos (
    id             bigserial PRIMARY KEY,
    empresa_id     bigint NOT NULL,
    proyecto_id    bigint NOT NULL,
    carpeta_id     bigint NOT NULL,
    nombre         text NOT NULL,
    extension      text NOT NULL DEFAULT '',
    mime           text NOT NULL,
    visible_cliente boolean NOT NULL DEFAULT false,
    estado_plano   text NOT NULL DEFAULT 'borrador'
                   CHECK (estado_plano IN ('borrador', 'en_revision', 'aprobado')),
    en_papelera_en timestamptz,
    version_actual_id bigint,
    creado_por     bigint REFERENCES usuarios(id),
    creado_en      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (empresa_id, id),
    FOREIGN KEY (empresa_id, proyecto_id, carpeta_id) REFERENCES carpetas(empresa_id, proyecto_id, id)
);

CREATE INDEX archivos_proyecto_idx ON archivos (empresa_id, proyecto_id);

CREATE TABLE versiones_archivo (
    id           bigserial PRIMARY KEY,
    empresa_id   bigint NOT NULL,
    archivo_id   bigint NOT NULL,
    numero       integer NOT NULL CHECK (numero > 0),
    sha256       text NOT NULL,
    tamano_bytes bigint NOT NULL CHECK (tamano_bytes >= 0),
    mime         text NOT NULL,
    origen       text NOT NULL CHECK (origen IN ('subida', 'agente', 'sesion')),
    derivados    jsonb NOT NULL DEFAULT '{}'::jsonb,
    subida_por   bigint REFERENCES usuarios(id),
    creada_en    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (archivo_id, numero),
    UNIQUE (empresa_id, archivo_id, id),
    FOREIGN KEY (empresa_id, archivo_id) REFERENCES archivos(empresa_id, id)
);

ALTER TABLE archivos ADD CONSTRAINT archivos_version_actual_fk
    FOREIGN KEY (empresa_id, id, version_actual_id) REFERENCES versiones_archivo(empresa_id, archivo_id, id)
    DEFERRABLE INITIALLY DEFERRED;

INSERT INTO carpetas (empresa_id, proyecto_id, nombre, posicion)
SELECT p.empresa_id, p.id, plantilla.nombre, plantilla.orden - 1
  FROM proyectos p
  JOIN tipos_proyecto t ON t.id = p.tipo_proyecto_id AND t.empresa_id = p.empresa_id
 CROSS JOIN LATERAL jsonb_array_elements_text(t.plantilla_carpetas) WITH ORDINALITY AS plantilla(nombre, orden)
 ORDER BY p.id, plantilla.orden
 ON CONFLICT (proyecto_id, padre_id, nombre) DO NOTHING;
