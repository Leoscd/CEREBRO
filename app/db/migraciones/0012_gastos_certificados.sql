ALTER TABLE archivos ADD UNIQUE (empresa_id, proyecto_id, id);
ALTER TABLE items_presupuesto ADD UNIQUE (empresa_id, presupuesto_id, id);

CREATE TABLE gastos (
    id                bigserial PRIMARY KEY,
    empresa_id        bigint NOT NULL,
    proyecto_id       bigint NOT NULL,
    fecha             date NOT NULL,
    descripcion       text NOT NULL CHECK (btrim(descripcion) <> ''),
    importe_centavos  bigint NOT NULL CHECK (importe_centavos > 0),
    proveedor_id      bigint,
    rubro             text NOT NULL DEFAULT '',
    archivo_id        bigint,
    cargado_por       bigint NOT NULL,
    creado_en         timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (empresa_id, proyecto_id) REFERENCES proyectos (empresa_id, id),
    FOREIGN KEY (empresa_id, proveedor_id) REFERENCES proveedores (empresa_id, id),
    FOREIGN KEY (empresa_id, proyecto_id, archivo_id) REFERENCES archivos (empresa_id, proyecto_id, id),
    FOREIGN KEY (empresa_id, cargado_por) REFERENCES usuarios (empresa_id, id)
);
CREATE INDEX gastos_por_proyecto ON gastos (empresa_id, proyecto_id, fecha DESC, id DESC);

CREATE TABLE certificados (
    id              bigserial PRIMARY KEY,
    empresa_id      bigint NOT NULL,
    presupuesto_id  bigint NOT NULL,
    numero          integer NOT NULL CHECK (numero > 0),
    periodo         date NOT NULL CHECK (extract(day FROM periodo) = 1),
    estado          text NOT NULL DEFAULT 'borrador' CHECK (estado IN ('borrador', 'emitido')),
    creado_en       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (empresa_id, presupuesto_id, numero),
    UNIQUE (empresa_id, presupuesto_id, id),
    FOREIGN KEY (empresa_id, presupuesto_id) REFERENCES presupuestos (empresa_id, id)
);
CREATE UNIQUE INDEX certificado_un_borrador ON certificados (empresa_id,presupuesto_id) WHERE estado='borrador';

CREATE TABLE certificado_items (
    empresa_id           bigint NOT NULL,
    presupuesto_id       bigint NOT NULL,
    certificado_id       bigint NOT NULL,
    item_presupuesto_id  bigint NOT NULL,
    avance_pb            integer NOT NULL CHECK (avance_pb BETWEEN 0 AND 10000),
    PRIMARY KEY (empresa_id, presupuesto_id, certificado_id, item_presupuesto_id),
    FOREIGN KEY (empresa_id,presupuesto_id,certificado_id)
        REFERENCES certificados (empresa_id,presupuesto_id,id) ON DELETE CASCADE,
    FOREIGN KEY (empresa_id,presupuesto_id,item_presupuesto_id)
        REFERENCES items_presupuesto (empresa_id,presupuesto_id,id)
);

CREATE FUNCTION proteger_certificado() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    ultimo integer;
BEGIN
    IF TG_OP <> 'INSERT' AND OLD.estado='emitido' THEN
        IF TG_OP='UPDATE' AND NEW IS NOT DISTINCT FROM OLD THEN
            RETURN NEW;
        END IF;
        RAISE EXCEPTION 'El certificado emitido es inmutable';
    END IF;
    IF TG_OP='DELETE' THEN
        RETURN OLD;
    END IF;
    IF TG_OP='UPDATE' AND (NEW.empresa_id, NEW.presupuesto_id, NEW.numero)
                         IS DISTINCT FROM (OLD.empresa_id, OLD.presupuesto_id, OLD.numero) THEN
        RAISE EXCEPTION 'El certificado debe conservar su presupuesto y número';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM presupuestos WHERE empresa_id=NEW.empresa_id AND id=NEW.presupuesto_id
            AND estado='emitido' FOR UPDATE
    ) THEN
        RAISE EXCEPTION 'Solo se puede certificar un presupuesto emitido';
    END IF;
    IF TG_OP='INSERT' THEN
        SELECT coalesce(max(numero),0) INTO ultimo FROM certificados
            WHERE empresa_id=NEW.empresa_id AND presupuesto_id=NEW.presupuesto_id;
        IF NEW.estado<>'borrador' OR NEW.numero<>ultimo+1 THEN
            RAISE EXCEPTION 'Creá el próximo certificado como borrador';
        END IF;
    ELSIF NEW.estado='emitido' AND EXISTS (
        SELECT 1 FROM items_presupuesto i WHERE i.empresa_id=NEW.empresa_id AND i.presupuesto_id=NEW.presupuesto_id
          AND (i.precio_emitido_centavos IS NULL OR NOT EXISTS (
              SELECT 1 FROM certificado_items d WHERE d.empresa_id=i.empresa_id AND d.presupuesto_id=i.presupuesto_id
                AND d.certificado_id=NEW.id AND d.item_presupuesto_id=i.id))
    ) THEN
        RAISE EXCEPTION 'Falta un importe emitido o el avance de un ítem';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER certificado_inmutable BEFORE INSERT OR UPDATE OR DELETE ON certificados
    FOR EACH ROW EXECUTE FUNCTION proteger_certificado();

CREATE FUNCTION proteger_detalle_de_certificado() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    empresa_anterior bigint;
    certificado_anterior bigint;
    empresa_nueva bigint;
    certificado_nuevo bigint;
    padre record;
    numero_actual integer;
    avance_anterior integer;
BEGIN
    IF TG_OP<>'INSERT' THEN
        empresa_anterior := OLD.empresa_id;
        certificado_anterior := OLD.certificado_id;
    END IF;
    IF TG_OP<>'DELETE' THEN
        empresa_nueva := NEW.empresa_id;
        certificado_nuevo := NEW.certificado_id;
    END IF;
    FOR padre IN SELECT id,estado,numero FROM certificados
        WHERE (empresa_id,id) IN ((empresa_anterior,certificado_anterior),(empresa_nueva,certificado_nuevo))
        ORDER BY empresa_id,id FOR UPDATE
    LOOP
        IF padre.estado='emitido' THEN
            RAISE EXCEPTION 'El certificado emitido es inmutable';
        END IF;
        IF padre.id=certificado_nuevo THEN
            numero_actual := padre.numero;
        END IF;
    END LOOP;
    IF TG_OP='DELETE' THEN
        RETURN OLD;
    END IF;
    SELECT coalesce(max(d.avance_pb),0) INTO avance_anterior
      FROM certificado_items d JOIN certificados c
        ON (c.empresa_id,c.presupuesto_id,c.id)=(d.empresa_id,d.presupuesto_id,d.certificado_id)
     WHERE d.empresa_id=NEW.empresa_id AND d.presupuesto_id=NEW.presupuesto_id
       AND d.item_presupuesto_id=NEW.item_presupuesto_id AND c.estado='emitido' AND c.numero<numero_actual;
    IF NEW.avance_pb<avance_anterior THEN
        RAISE EXCEPTION 'El avance no puede bajar respecto del certificado anterior';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER detalle_de_certificado_inmutable BEFORE INSERT OR UPDATE OR DELETE ON certificado_items
    FOR EACH ROW EXECUTE FUNCTION proteger_detalle_de_certificado();

CREATE FUNCTION proteger_vaciado_de_certificados() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM certificados WHERE estado='emitido') THEN
        RAISE EXCEPTION 'El certificado emitido es inmutable';
    END IF;
    RETURN NULL;
END;
$$;
CREATE TRIGGER certificados_no_vaciar_emitidos BEFORE TRUNCATE ON certificados
    FOR EACH STATEMENT EXECUTE FUNCTION proteger_vaciado_de_certificados();
CREATE TRIGGER certificado_items_no_vaciar_emitidos BEFORE TRUNCATE ON certificado_items
    FOR EACH STATEMENT EXECUTE FUNCTION proteger_vaciado_de_certificados();
