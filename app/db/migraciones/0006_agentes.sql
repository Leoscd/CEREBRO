ALTER TABLE usuarios ADD UNIQUE (empresa_id, id);

CREATE TABLE conversaciones (
    id          bigserial PRIMARY KEY,
    empresa_id  bigint NOT NULL,
    proyecto_id bigint NOT NULL,
    usuario_id  bigint NOT NULL,
    agente      text NOT NULL,
    resumen     text NOT NULL DEFAULT '',
    creada_en   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (empresa_id, id),
    UNIQUE (empresa_id, proyecto_id, usuario_id, agente),
    FOREIGN KEY (empresa_id, proyecto_id) REFERENCES proyectos(empresa_id, id),
    FOREIGN KEY (empresa_id, usuario_id) REFERENCES usuarios(empresa_id, id)
);

CREATE TABLE mensajes (
    id              bigserial PRIMARY KEY,
    empresa_id      bigint NOT NULL,
    conversacion_id bigint NOT NULL,
    rol             text NOT NULL CHECK (rol IN ('user', 'assistant')),
    contenido       text NOT NULL,
    citas           jsonb NOT NULL DEFAULT '[]'::jsonb,
    creado_en       timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (empresa_id, conversacion_id) REFERENCES conversaciones(empresa_id, id)
);
CREATE INDEX mensajes_conversacion_idx ON mensajes (empresa_id, conversacion_id, id);

CREATE TABLE agent_runs (
    id              bigserial PRIMARY KEY,
    empresa_id      bigint NOT NULL,
    conversacion_id bigint NOT NULL,
    modelo          text NOT NULL,
    estado          text NOT NULL CHECK (estado IN ('en_curso', 'hecho', 'fallido')),
    tokens_entrada  bigint NOT NULL DEFAULT 0,
    tokens_salida   bigint NOT NULL DEFAULT 0,
    estado_sdk      jsonb NOT NULL DEFAULT '{}'::jsonb,
    creado_en       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (empresa_id, id),
    FOREIGN KEY (empresa_id, conversacion_id) REFERENCES conversaciones(empresa_id, id)
);
CREATE INDEX agent_runs_conversacion_idx ON agent_runs (empresa_id, conversacion_id, id);

CREATE TABLE tool_calls (
    id                bigserial PRIMARY KEY,
    empresa_id        bigint NOT NULL,
    agent_run_id      bigint NOT NULL,
    herramienta       text NOT NULL,
    argumentos        jsonb NOT NULL,
    resultado_resumen text NOT NULL,
    estado            text NOT NULL,
    creado_en         timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (empresa_id, agent_run_id) REFERENCES agent_runs(empresa_id, id)
);
CREATE INDEX tool_calls_run_idx ON tool_calls (empresa_id, agent_run_id, id);
