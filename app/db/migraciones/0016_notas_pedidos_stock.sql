CREATE TABLE notas_obra (
    id bigserial PRIMARY KEY,
    empresa_id bigint NOT NULL,
    proyecto_id bigint NOT NULL,
    tipo text NOT NULL CHECK (tipo IN ('orden_servicio','nota_pedido')),
    numero bigint NOT NULL CHECK (numero > 0),
    fecha date NOT NULL,
    emisor text NOT NULL CHECK (btrim(emisor) <> ''),
    destinatario text NOT NULL CHECK (btrim(destinatario) <> ''),
    asunto text NOT NULL CHECK (btrim(asunto) <> ''),
    texto text NOT NULL CHECK (btrim(texto) <> ''),
    plazo date CHECK (plazo IS NULL OR plazo >= fecha),
    estado text NOT NULL DEFAULT 'abierta' CHECK (estado IN ('abierta','respondida','cerrada')),
    reporte_id bigint,
    UNIQUE (proyecto_id, tipo, numero),
    FOREIGN KEY (empresa_id, proyecto_id) REFERENCES proyectos(empresa_id, id),
    FOREIGN KEY (empresa_id, proyecto_id, reporte_id) REFERENCES reportes_obra(empresa_id, proyecto_id, id)
);

CREATE TABLE pedidos_material (
    id bigserial PRIMARY KEY,
    empresa_id bigint NOT NULL,
    proyecto_id bigint NOT NULL,
    tarea_id bigint NOT NULL,
    material text NOT NULL,
    estado text NOT NULL CHECK (estado IN ('pendiente','pedido','recibido','no_aplica')),
    fecha date NOT NULL,
    fecha_entrega date CHECK (fecha_entrega IS NULL OR fecha_entrega >= fecha),
    UNIQUE (empresa_id, proyecto_id, tarea_id, material),
    FOREIGN KEY (empresa_id, proyecto_id, tarea_id, material)
        REFERENCES materiales_tarea(empresa_id, proyecto_id, tarea_id, nombre)
);

CREATE FUNCTION clave_stock_obra(text) RETURNS text LANGUAGE sql IMMUTABLE STRICT AS $$
    SELECT translate(lower(regexp_replace(btrim($1), '\s+', ' ', 'g')), 'áéíóúü', 'aeiouu')
$$;

CREATE TABLE stock_obra (
    id bigserial PRIMARY KEY,
    empresa_id bigint NOT NULL,
    proyecto_id bigint NOT NULL,
    material text NOT NULL CHECK (btrim(material) <> ''),
    unidad text NOT NULL CHECK (btrim(unidad) <> ''),
    material_clave text GENERATED ALWAYS AS (clave_stock_obra(material)) STORED,
    unidad_clave text GENERATED ALWAYS AS (clave_stock_obra(unidad)) STORED,
    fecha date NOT NULL,
    cantidad numeric(18,4) NOT NULL CHECK (cantidad >= 0 AND cantidad <> 'NaN'::numeric),
    reporte_id bigint,
    FOREIGN KEY (empresa_id, proyecto_id) REFERENCES proyectos(empresa_id, id),
    FOREIGN KEY (empresa_id, proyecto_id, reporte_id) REFERENCES reportes_obra(empresa_id, proyecto_id, id)
);

CREATE INDEX stock_obra_vigente_idx ON stock_obra(empresa_id, proyecto_id, material_clave, unidad_clave, fecha DESC, id DESC);

CREATE FUNCTION stock_obra_inmutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'El historial de stock solo permite inserciones' USING ERRCODE = '23514';
END;
$$;

CREATE TRIGGER stock_obra_solo_inserciones BEFORE UPDATE OR DELETE OR TRUNCATE ON stock_obra
FOR EACH STATEMENT EXECUTE FUNCTION stock_obra_inmutable();

CREATE FUNCTION ingresar_stock_parte_confirmado() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO stock_obra (empresa_id, proyecto_id, material, unidad, fecha, cantidad, reporte_id)
    SELECT NEW.empresa_id, NEW.proyecto_id, min(btrim(m->>'material')), min(btrim(m->>'unidad')), NEW.fecha,
           sum((m->>'cantidad')::numeric), NEW.id
      FROM jsonb_array_elements(NEW.datos->'materiales'->'ingresos') AS m
     WHERE btrim(m->>'material') <> '' AND btrim(m->>'unidad') <> '' AND (m->>'cantidad')::numeric > 0
     GROUP BY clave_stock_obra(m->>'material'), clave_stock_obra(m->>'unidad');
    RETURN NEW;
END;
$$;

CREATE TRIGGER stock_desde_parte_confirmado AFTER UPDATE OF estado ON reportes_obra
FOR EACH ROW WHEN (OLD.estado='borrador' AND NEW.estado='confirmado')
EXECUTE FUNCTION ingresar_stock_parte_confirmado();
