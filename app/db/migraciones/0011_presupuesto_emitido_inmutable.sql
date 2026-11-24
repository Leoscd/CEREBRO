CREATE FUNCTION proteger_presupuesto_emitido() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.estado = 'emitido' THEN
        IF TG_OP = 'UPDATE' AND NEW IS NOT DISTINCT FROM OLD THEN
            RETURN NEW;
        END IF;
        RAISE EXCEPTION 'El presupuesto emitido es inmutable';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER presupuesto_emitido_inmutable BEFORE UPDATE OR DELETE ON presupuestos
    FOR EACH ROW EXECUTE FUNCTION proteger_presupuesto_emitido();

CREATE FUNCTION proteger_detalle_de_presupuesto() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    empresa_anterior bigint;
    presupuesto_anterior bigint;
    empresa_nueva bigint;
    presupuesto_nuevo bigint;
    estado_padre text;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        empresa_anterior := OLD.empresa_id;
        presupuesto_anterior := OLD.presupuesto_id;
    END IF;
    IF TG_OP <> 'DELETE' THEN
        empresa_nueva := NEW.empresa_id;
        presupuesto_nuevo := NEW.presupuesto_id;
    END IF;
    -- Bloquea ambos padres en orden estable si se mueve un rubro o ítem.
    FOR estado_padre IN
        SELECT estado FROM presupuestos
         WHERE (empresa_id, id) IN ((empresa_anterior, presupuesto_anterior), (empresa_nueva, presupuesto_nuevo))
         ORDER BY empresa_id, id FOR UPDATE
    LOOP
        IF estado_padre = 'emitido' THEN
            RAISE EXCEPTION 'El presupuesto emitido es inmutable';
        END IF;
    END LOOP;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER rubros_de_emitido_inmutables BEFORE INSERT OR UPDATE OR DELETE ON rubros_presupuesto
    FOR EACH ROW EXECUTE FUNCTION proteger_detalle_de_presupuesto();
CREATE TRIGGER items_de_emitido_inmutables BEFORE INSERT OR UPDATE OR DELETE ON items_presupuesto
    FOR EACH ROW EXECUTE FUNCTION proteger_detalle_de_presupuesto();

CREATE FUNCTION proteger_vaciado_de_presupuestos() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM presupuestos WHERE estado = 'emitido') THEN
        RAISE EXCEPTION 'El presupuesto emitido es inmutable';
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER presupuestos_no_vaciar_emitidos BEFORE TRUNCATE ON presupuestos
    FOR EACH STATEMENT EXECUTE FUNCTION proteger_vaciado_de_presupuestos();
CREATE TRIGGER rubros_no_vaciar_emitidos BEFORE TRUNCATE ON rubros_presupuesto
    FOR EACH STATEMENT EXECUTE FUNCTION proteger_vaciado_de_presupuestos();
CREATE TRIGGER items_no_vaciar_emitidos BEFORE TRUNCATE ON items_presupuesto
    FOR EACH STATEMENT EXECUTE FUNCTION proteger_vaciado_de_presupuestos();
