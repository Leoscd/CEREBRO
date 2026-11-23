CREATE TABLE apus (
    id          bigserial PRIMARY KEY,
    empresa_id  bigint NOT NULL REFERENCES empresas(id),
    codigo      text NOT NULL CHECK (btrim(codigo) <> ''),
    descripcion text NOT NULL CHECK (btrim(descripcion) <> ''),
    unidad      text NOT NULL CHECK (btrim(unidad) <> ''),
    rubro       text NOT NULL DEFAULT '',
    activo      boolean NOT NULL DEFAULT true,
    UNIQUE (empresa_id, codigo),
    UNIQUE (empresa_id, id)
);

CREATE TABLE apu_insumos (
    empresa_id       bigint NOT NULL,
    apu_id           bigint NOT NULL,
    material_id      bigint NOT NULL,
    cantidad         numeric(14,4) NOT NULL CHECK (cantidad > 0 AND cantidad <> 'NaN'::numeric),
    desperdicio_pb   integer NOT NULL DEFAULT 0 CHECK (desperdicio_pb >= 0),
    PRIMARY KEY (empresa_id, apu_id, material_id),
    FOREIGN KEY (empresa_id, apu_id) REFERENCES apus (empresa_id, id) ON DELETE CASCADE,
    FOREIGN KEY (empresa_id, material_id) REFERENCES materiales (empresa_id, id)
);
