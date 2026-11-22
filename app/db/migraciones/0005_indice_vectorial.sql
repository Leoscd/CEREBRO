CREATE INDEX chunks_embedding_hnsw_idx ON chunks USING hnsw (embedding vector_cosine_ops);

INSERT INTO jobs (empresa_id, tipo, payload)
SELECT DISTINCT c.empresa_id, 'chunks.embeber', jsonb_build_object('version_id', c.version_id)
  FROM chunks c JOIN archivos a ON a.empresa_id = c.empresa_id AND a.proyecto_id = c.proyecto_id
                               AND a.version_actual_id = c.version_id
 WHERE c.embedding IS NULL;
