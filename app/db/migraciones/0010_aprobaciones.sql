ALTER TABLE agent_runs DROP CONSTRAINT agent_runs_estado_check;
ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_estado_check
    CHECK (estado IN ('en_curso', 'esperando_aprobacion', 'hecho', 'fallido'));

ALTER TABLE tool_calls ADD COLUMN sdk_call_id text;
ALTER TABLE tool_calls ADD COLUMN decidido_en timestamptz;
CREATE UNIQUE INDEX tool_calls_llamada_sdk
    ON tool_calls (empresa_id, agent_run_id, sdk_call_id) WHERE sdk_call_id IS NOT NULL;
