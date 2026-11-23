CREATE TABLE materiales (
    id          bigserial PRIMARY KEY,
    empresa_id  bigint NOT NULL REFERENCES empresas(id),
    codigo      text NOT NULL CHECK (btrim(codigo) <> ''),
    nombre      text NOT NULL CHECK (btrim(nombre) <> ''),
    unidad      text NOT NULL CHECK (btrim(unidad) <> ''),
    tipo        text NOT NULL CHECK (tipo IN ('material', 'mano_obra', 'equipo')),
    rubro       text NOT NULL DEFAULT '',
    activo      boolean NOT NULL DEFAULT true,
    UNIQUE (empresa_id, codigo),
    UNIQUE (empresa_id, id)
);

CREATE TABLE proveedores (
    id          bigserial PRIMARY KEY,
    empresa_id  bigint NOT NULL REFERENCES empresas(id),
    nombre      text NOT NULL CHECK (btrim(nombre) <> ''),
    cuit        text NOT NULL DEFAULT '',
    contacto    text NOT NULL DEFAULT '',
    activo      boolean NOT NULL DEFAULT true,
    UNIQUE (empresa_id, id)
);

CREATE TABLE precios (
    id                bigserial PRIMARY KEY,
    empresa_id        bigint NOT NULL REFERENCES empresas(id),
    material_id       bigint NOT NULL,
    proveedor_id      bigint,
    precio_centavos   bigint NOT NULL CHECK (precio_centavos > 0),
    vigente_desde     timestamptz NOT NULL,
    fuente            text NOT NULL CHECK (fuente IN ('manual', 'excel', 'agente')),
    cargado_por       bigint NOT NULL,
    creado_en         timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (empresa_id, material_id) REFERENCES materiales (empresa_id, id),
    FOREIGN KEY (empresa_id, proveedor_id) REFERENCES proveedores (empresa_id, id),
    FOREIGN KEY (empresa_id, cargado_por) REFERENCES usuarios (empresa_id, id)
);
CREATE INDEX precios_vigencia ON precios (empresa_id, material_id, vigente_desde DESC, id DESC);

CREATE FUNCTION precios_inmutables() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'El historial de precios es inmutable';
END;
$$;
CREATE TRIGGER precios_solo_insertar BEFORE UPDATE OR DELETE ON precios
    FOR EACH ROW EXECUTE FUNCTION precios_inmutables();
CREATE TRIGGER precios_no_vaciar BEFORE TRUNCATE ON precios
    FOR EACH STATEMENT EXECUTE FUNCTION precios_inmutables();

CREATE VIEW v_cambios_precio AS
SELECT id, empresa_id, material_id, proveedor_id, fuente, vigente_desde,
       anterior_centavos, actual_centavos,
       round((actual_centavos::numeric - anterior_centavos) * 10000 / anterior_centavos) AS variacion_pb
  FROM (
    SELECT id, empresa_id, material_id, proveedor_id, fuente, vigente_desde,
           lag(precio_centavos) OVER (
               PARTITION BY empresa_id, material_id ORDER BY vigente_desde, id
           ) AS anterior_centavos,
           precio_centavos AS actual_centavos
      FROM precios
  ) cambios;

CREATE TABLE indices_costo (
    id          bigserial PRIMARY KEY,
    empresa_id  bigint NOT NULL REFERENCES empresas(id),
    nombre      text NOT NULL CHECK (btrim(nombre) <> ''),
    periodo     date NOT NULL CHECK (extract(day FROM periodo) = 1),
    valor       numeric(12,4) NOT NULL CHECK (valor > 0 AND valor <> 'NaN'::numeric),
    UNIQUE (empresa_id, nombre, periodo)
);
