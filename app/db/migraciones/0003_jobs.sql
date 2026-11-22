CREATE TABLE jobs (
    id               bigserial PRIMARY KEY,
    empresa_id       bigint NOT NULL REFERENCES empresas(id),
    tipo             text NOT NULL,
    payload          jsonb NOT NULL,
    estado           text NOT NULL DEFAULT 'pendiente'
                     CHECK (estado IN ('pendiente', 'en_curso', 'hecho', 'fallido')),
    intentos         integer NOT NULL DEFAULT 0 CHECK (intentos >= 0),
    max_intentos     integer NOT NULL DEFAULT 3 CHECK (max_intentos > 0),
    error            text,
    disponible_desde timestamptz NOT NULL DEFAULT now(),
    tomado_en        timestamptz,
    terminado_en     timestamptz,
    creado_en        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX jobs_pendientes_idx ON jobs (disponible_desde, id) WHERE estado = 'pendiente';
CREATE INDEX jobs_en_curso_idx ON jobs (tomado_en) WHERE estado = 'en_curso';
