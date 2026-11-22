CREATE TABLE biblioteca_documentos (
    id             bigserial PRIMARY KEY,
    empresa_id     bigint NOT NULL REFERENCES empresas(id),
    titulo         text NOT NULL,
    tipo           text NOT NULL CHECK (tipo IN ('normativa', 'criterio', 'pliego', 'leccion')),
    version        text NOT NULL,
    estado         text NOT NULL DEFAULT 'borrador' CHECK (estado IN ('borrador', 'aprobado', 'retirado')),
    sha256         text NOT NULL,
    nombre_archivo text NOT NULL,
    subido_por     bigint REFERENCES usuarios(id),
    aprobado_por   bigint REFERENCES usuarios(id),
    aprobado_en    timestamptz,
    creado_en      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (empresa_id, id)
);

ALTER TABLE versiones_archivo ADD UNIQUE (empresa_id, id);

CREATE TABLE chunks (
    id            bigserial PRIMARY KEY,
    empresa_id    bigint NOT NULL REFERENCES empresas(id),
    proyecto_id   bigint,
    version_id    bigint,
    biblioteca_id bigint,
    pagina        integer NOT NULL CHECK (pagina >= 1),
    orden         integer NOT NULL CHECK (orden >= 0),
    texto         text NOT NULL,
    tsv           tsvector GENERATED ALWAYS AS (to_tsvector('spanish', texto)) STORED,
    embedding     vector(384),
    creado_en     timestamptz NOT NULL DEFAULT now(),
    CHECK ((proyecto_id IS NOT NULL AND version_id IS NOT NULL AND biblioteca_id IS NULL)
        OR (proyecto_id IS NULL AND version_id IS NULL AND biblioteca_id IS NOT NULL)),
    FOREIGN KEY (empresa_id, proyecto_id) REFERENCES proyectos(empresa_id, id),
    FOREIGN KEY (empresa_id, version_id) REFERENCES versiones_archivo(empresa_id, id),
    FOREIGN KEY (empresa_id, biblioteca_id) REFERENCES biblioteca_documentos(empresa_id, id),
    UNIQUE (version_id, pagina, orden),
    UNIQUE (biblioteca_id, pagina, orden)
);

CREATE INDEX chunks_tsv_idx ON chunks USING gin (tsv);
CREATE INDEX chunks_proyecto_idx ON chunks (empresa_id, proyecto_id);

-- Incluye los PDF vigentes cargados antes de habilitar la indexación.
INSERT INTO jobs (empresa_id, tipo, payload)
SELECT v.empresa_id, 'archivo.indexar', jsonb_build_object('version_id', v.id)
  FROM archivos a
  JOIN versiones_archivo v ON v.empresa_id = a.empresa_id AND v.archivo_id = a.id AND v.id = a.version_actual_id
 WHERE coalesce(v.derivados->'meta'->>'mime_real', v.mime) = 'application/pdf';
