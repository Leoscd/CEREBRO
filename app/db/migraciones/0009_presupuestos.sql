CREATE TABLE presupuestos (
    id                    bigserial PRIMARY KEY,
    empresa_id            bigint NOT NULL,
    proyecto_id           bigint NOT NULL,
    raiz_id               bigint,
    nombre                text NOT NULL CHECK (btrim(nombre) <> ''),
    version               integer NOT NULL DEFAULT 1 CHECK (version >= 1),
    estado                text NOT NULL DEFAULT 'borrador' CHECK (estado IN ('borrador', 'emitido')),
    fecha_precios         date NOT NULL,
    gastos_generales_pb   integer NOT NULL DEFAULT 0 CHECK (gastos_generales_pb >= 0),
    beneficio_pb          integer NOT NULL DEFAULT 0 CHECK (beneficio_pb >= 0),
    impuestos_pb          integer NOT NULL DEFAULT 0 CHECK (impuestos_pb >= 0),
    creado_por            bigint NOT NULL,
    creado_en             timestamptz NOT NULL DEFAULT now(),
    emitido_en            timestamptz,
    UNIQUE (empresa_id, id),
    UNIQUE (empresa_id, proyecto_id, id),
    CHECK ((version = 1) = (raiz_id IS NULL)),
    CHECK ((estado = 'emitido') = (emitido_en IS NOT NULL)),
    FOREIGN KEY (empresa_id, proyecto_id) REFERENCES proyectos (empresa_id, id),
    FOREIGN KEY (empresa_id, proyecto_id, raiz_id) REFERENCES presupuestos (empresa_id, proyecto_id, id),
    FOREIGN KEY (empresa_id, creado_por) REFERENCES usuarios (empresa_id, id)
);
CREATE UNIQUE INDEX presupuesto_version_unica
    ON presupuestos (empresa_id, proyecto_id, coalesce(raiz_id, id), version);

CREATE TABLE rubros_presupuesto (
    id             bigserial PRIMARY KEY,
    empresa_id     bigint NOT NULL,
    presupuesto_id bigint NOT NULL,
    nombre         text NOT NULL CHECK (btrim(nombre) <> ''),
    orden          integer NOT NULL CHECK (orden > 0),
    UNIQUE (empresa_id, presupuesto_id, id),
    UNIQUE (empresa_id, presupuesto_id, nombre),
    FOREIGN KEY (empresa_id, presupuesto_id) REFERENCES presupuestos (empresa_id, id) ON DELETE CASCADE
);

CREATE TABLE items_presupuesto (
    id                        bigserial PRIMARY KEY,
    empresa_id                bigint NOT NULL,
    presupuesto_id            bigint NOT NULL,
    rubro_id                  bigint NOT NULL,
    descripcion               text NOT NULL CHECK (btrim(descripcion) <> ''),
    unidad                    text NOT NULL CHECK (btrim(unidad) <> ''),
    cantidad                  numeric(14,4) NOT NULL CHECK (cantidad <> 'NaN'::numeric),
    apu_id                    bigint,
    precio_unitario_centavos  bigint CHECK (precio_unitario_centavos >= 0),
    precio_emitido_centavos   bigint CHECK (precio_emitido_centavos >= 0),
    metadatos_emision         jsonb NOT NULL DEFAULT '{}'::jsonb,
    origen_cantidad           text NOT NULL DEFAULT 'manual' CHECK (origen_cantidad IN ('manual', 'revit', 'autocad')),
    orden                     integer NOT NULL CHECK (orden > 0),
    CHECK ((apu_id IS NULL) <> (precio_unitario_centavos IS NULL)),
    FOREIGN KEY (empresa_id, presupuesto_id, rubro_id)
        REFERENCES rubros_presupuesto (empresa_id, presupuesto_id, id) ON DELETE CASCADE,
    FOREIGN KEY (empresa_id, apu_id) REFERENCES apus (empresa_id, id)
);
CREATE INDEX items_por_rubro ON items_presupuesto (empresa_id, presupuesto_id, rubro_id, orden, id);
