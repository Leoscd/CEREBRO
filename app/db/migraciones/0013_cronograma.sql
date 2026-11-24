CREATE TABLE tareas_obra (
    id                    bigserial PRIMARY KEY,
    empresa_id            bigint NOT NULL,
    proyecto_id           bigint NOT NULL,
    codigo                text NOT NULL CHECK (btrim(codigo) <> ''),
    nombre                text NOT NULL CHECK (btrim(nombre) <> ''),
    rubro                 text NOT NULL DEFAULT '',
    inicio                date NOT NULL,
    fin                   date NOT NULL CHECK (fin >= inicio),
    critica               boolean NOT NULL DEFAULT false,
    presupuesto_id        bigint,
    item_presupuesto_id   bigint,
    orden                 integer NOT NULL DEFAULT 1,
    UNIQUE (empresa_id, proyecto_id, codigo),
    UNIQUE (empresa_id, proyecto_id, id),
    UNIQUE (empresa_id, proyecto_id, item_presupuesto_id),
    CHECK ((presupuesto_id IS NULL) = (item_presupuesto_id IS NULL)),
    FOREIGN KEY (empresa_id, proyecto_id) REFERENCES proyectos (empresa_id, id),
    FOREIGN KEY (empresa_id, proyecto_id, presupuesto_id) REFERENCES presupuestos (empresa_id, proyecto_id, id),
    FOREIGN KEY (empresa_id, presupuesto_id, item_presupuesto_id) REFERENCES items_presupuesto (empresa_id, presupuesto_id, id)
);

CREATE TABLE materiales_tarea (
    id            bigserial PRIMARY KEY,
    empresa_id    bigint NOT NULL,
    proyecto_id   bigint NOT NULL,
    tarea_id      bigint NOT NULL,
    nombre        text NOT NULL CHECK (btrim(nombre) <> ''),
    cantidad      numeric(14,4) NOT NULL CHECK (cantidad > 0 AND cantidad <> 'NaN'::numeric),
    unidad        text NOT NULL CHECK (btrim(unidad) <> ''),
    plazo_dias    integer NOT NULL CHECK (plazo_dias >= 0),
    UNIQUE (empresa_id, proyecto_id, tarea_id, nombre),
    FOREIGN KEY (empresa_id, proyecto_id, tarea_id) REFERENCES tareas_obra (empresa_id, proyecto_id, id)
);

CREATE TABLE avances_tarea (
    id             bigserial PRIMARY KEY,
    empresa_id     bigint NOT NULL,
    proyecto_id    bigint NOT NULL,
    tarea_id       bigint NOT NULL,
    fecha          date NOT NULL,
    avance_pb      integer NOT NULL CHECK (avance_pb BETWEEN 0 AND 10000),
    registrado_por bigint NOT NULL,
    creado_en      timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (empresa_id, proyecto_id, tarea_id) REFERENCES tareas_obra (empresa_id, proyecto_id, id),
    FOREIGN KEY (empresa_id, registrado_por) REFERENCES usuarios (empresa_id, id)
);
CREATE INDEX avances_tarea_vigencia ON avances_tarea (empresa_id, proyecto_id, tarea_id, fecha DESC, id DESC);

CREATE FUNCTION avance_obra_inmutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'El historial de avances de obra es inmutable';
END;
$$;
CREATE TRIGGER avances_obra_solo_insertar BEFORE UPDATE OR DELETE ON avances_tarea
    FOR EACH ROW EXECUTE FUNCTION avance_obra_inmutable();
CREATE TRIGGER avances_obra_no_vaciar BEFORE TRUNCATE ON avances_tarea
    FOR EACH STATEMENT EXECUTE FUNCTION avance_obra_inmutable();

CREATE TABLE feriados (
    empresa_id bigint NOT NULL REFERENCES empresas(id),
    fecha      date NOT NULL,
    nombre     text NOT NULL CHECK (btrim(nombre) <> ''),
    PRIMARY KEY (empresa_id, fecha)
);

-- Fechas fijas del calendario de referencia, incluido el feriado de Tucumán.
CREATE FUNCTION obra_feriados_fijos() RETURNS TABLE (mes integer, dia integer, nombre text)
LANGUAGE sql IMMUTABLE AS $$
    VALUES (1,1,'Año Nuevo'::text), (3,24,'Día de la Memoria'), (4,2,'Día de Malvinas'),
           (5,1,'Día del Trabajador'), (5,25,'Revolución de Mayo'), (6,20,'Paso a la Inmortalidad de Belgrano'),
           (7,9,'Día de la Independencia'), (9,24,'Batalla de Tucumán'), (12,8,'Inmaculada Concepción'),
           (12,25,'Navidad');
$$;
CREATE FUNCTION sembrar_feriados_obra(empresa bigint) RETURNS void LANGUAGE sql AS $$
    INSERT INTO feriados(empresa_id,fecha,nombre)
    SELECT empresa, make_date(anio,f.mes,f.dia), f.nombre
      FROM generate_series(extract(year FROM current_date)::integer - 1,
                           extract(year FROM current_date)::integer + 1) anio
      CROSS JOIN obra_feriados_fijos() f
    ON CONFLICT DO NOTHING;
$$;
SELECT sembrar_feriados_obra(id) FROM empresas;
CREATE FUNCTION feriados_al_crear_empresa() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM sembrar_feriados_obra(NEW.id);
    RETURN NEW;
END;
$$;
CREATE TRIGGER empresa_siembra_feriados AFTER INSERT ON empresas
    FOR EACH ROW EXECUTE FUNCTION feriados_al_crear_empresa();
