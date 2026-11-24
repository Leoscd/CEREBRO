-- Las coordenadas del proyecto ya existen en 0001_base.sql.
CREATE TABLE audios_parte (
    id bigserial PRIMARY KEY,
    empresa_id bigint NOT NULL,
    proyecto_id bigint NOT NULL,
    reporte_id bigint NOT NULL,
    archivo_id bigint NOT NULL,
    version_id bigint NOT NULL,
    job_id bigint REFERENCES jobs(id),
    extension text NOT NULL CHECK (extension IN ('m4a','ogg','webm','mp3')),
    texto text,
    aceptado_en timestamptz,
    FOREIGN KEY (empresa_id, proyecto_id, reporte_id) REFERENCES reportes_obra(empresa_id, proyecto_id, id),
    FOREIGN KEY (empresa_id, archivo_id, version_id) REFERENCES versiones_archivo(empresa_id, archivo_id, id)
);

CREATE INDEX audios_parte_reporte_idx ON audios_parte (empresa_id, proyecto_id, reporte_id);
