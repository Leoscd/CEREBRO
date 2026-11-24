CREATE TABLE reportes_obra (
    id bigserial PRIMARY KEY,
    empresa_id bigint NOT NULL,
    proyecto_id bigint NOT NULL,
    fecha date NOT NULL,
    dt_id bigint NOT NULL REFERENCES usuarios(id),
    estado text NOT NULL DEFAULT 'borrador' CHECK (estado IN ('borrador', 'confirmado')),
    numero bigint CHECK (numero > 0),
    datos jsonb NOT NULL,
    confirmado_en timestamptz,
    UNIQUE (empresa_id, proyecto_id, id),
    UNIQUE (proyecto_id, fecha, dt_id),
    UNIQUE (proyecto_id, numero),
    FOREIGN KEY (empresa_id, proyecto_id) REFERENCES proyectos(empresa_id, id),
    CHECK ((estado = 'confirmado') = (numero IS NOT NULL AND confirmado_en IS NOT NULL)),
    CHECK ((numero IS NULL) = (confirmado_en IS NULL))
);

CREATE TABLE fotos_obra (
    id bigserial PRIMARY KEY,
    empresa_id bigint NOT NULL,
    proyecto_id bigint NOT NULL,
    reporte_id bigint NOT NULL,
    archivo_id bigint NOT NULL,
    version_id bigint NOT NULL,
    sha256 text NOT NULL,
    descripcion text NOT NULL DEFAULT '',
    tarea_id bigint,
    hora timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (empresa_id, proyecto_id, reporte_id) REFERENCES reportes_obra(empresa_id, proyecto_id, id),
    FOREIGN KEY (empresa_id, proyecto_id, tarea_id) REFERENCES tareas_obra(empresa_id, proyecto_id, id),
    FOREIGN KEY (empresa_id, archivo_id, version_id) REFERENCES versiones_archivo(empresa_id, archivo_id, id)
);

CREATE INDEX fotos_obra_parte_idx ON fotos_obra (empresa_id, proyecto_id, reporte_id);

CREATE FUNCTION proteger_parte_confirmado() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.estado = 'confirmado' THEN
        RAISE EXCEPTION 'El parte confirmado es inmutable' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER reportes_obra_confirmados_inmutables BEFORE UPDATE OR DELETE ON reportes_obra
FOR EACH ROW EXECUTE FUNCTION proteger_parte_confirmado();

CREATE FUNCTION proteger_fotos_parte_confirmado() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    parte_viejo bigint;
    parte_nuevo bigint;
    estado_parte text;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        parte_viejo := OLD.reporte_id;
    END IF;
    IF TG_OP <> 'DELETE' THEN
        parte_nuevo := NEW.reporte_id;
    END IF;
    FOR estado_parte IN SELECT estado FROM reportes_obra
        WHERE id IN (parte_viejo, parte_nuevo) ORDER BY id FOR UPDATE
    LOOP
        IF estado_parte = 'confirmado' THEN
            RAISE EXCEPTION 'Las fotos del parte confirmado son inmutables' USING ERRCODE = '23514';
        END IF;
    END LOOP;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER fotos_obra_confirmadas_inmutables BEFORE INSERT OR UPDATE OR DELETE ON fotos_obra
FOR EACH ROW EXECUTE FUNCTION proteger_fotos_parte_confirmado();

CREATE FUNCTION proteger_vaciado_partes_confirmados() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM reportes_obra WHERE estado = 'confirmado') THEN
        RAISE EXCEPTION 'Los partes y sus fotos confirmados son inmutables' USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER reportes_obra_no_vaciar BEFORE TRUNCATE ON reportes_obra
FOR EACH STATEMENT EXECUTE FUNCTION proteger_vaciado_partes_confirmados();
CREATE TRIGGER fotos_obra_no_vaciar BEFORE TRUNCATE ON fotos_obra
FOR EACH STATEMENT EXECUTE FUNCTION proteger_vaciado_partes_confirmados();
