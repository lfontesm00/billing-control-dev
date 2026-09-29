-- VALIDATION TARGET: dataset_dev_trusted_clinica_validacao. Do not run against the primary dataset.
-- Idempotent backfill of tb_trat_billing_control_doutor_clinica.
-- DO NOT EXECUTE without running 015_doctor_preflight.sql first and obtaining explicit authorization.
--
-- Strategy:
--   Wave 1 — insert pairs derived from doutores.id_clinica (historical origin field).
--   Wave 2 — insert pairs observed in consultas not yet covered by wave 1 or existing records.
--
-- Both waves use MERGE to guarantee idempotency: re-running this script is safe.
-- No existing record is deleted, updated, or overwritten.
-- data_inicio is set to the earliest known consulta date for wave-2 pairs; otherwise CURRENT_DATE().
-- Rollback plan: there is no physical rollback for BigQuery INSERT/MERGE without a snapshot.
--   To undo: DELETE FROM doutor_clinica WHERE origem_registro='BACKFILL_2026' -- logical rollback.
--   Record counts before and after are captured by 015_doctor_preflight and 017_doctor_clinic_reconciliation.

-- Wave 1: pairs from doutores.id_clinica missing in doutor_clinica.
MERGE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutor_clinica` AS target
USING (
  SELECT
    ABS(FARM_FINGERPRINT(CONCAT(CAST(d.id_doutor AS STRING), ':', CAST(d.id_clinica AS STRING)))) AS id_doutor_clinica,
    d.id_doutor,
    d.id_clinica,
    d.nome_doutor,
    CURRENT_DATE() AS data_inicio,
    NULL AS data_fim,
    d.flag_ativo
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutores` d
  WHERE d.id_clinica IS NOT NULL
) AS source
ON target.id_doutor = source.id_doutor AND target.id_clinica = source.id_clinica
WHEN NOT MATCHED THEN INSERT (
  id_doutor_clinica, id_doutor, id_clinica, nome_doutor, data_inicio, data_fim, flag_ativo, created_at, updated_at
) VALUES (
  source.id_doutor_clinica,
  source.id_doutor,
  source.id_clinica,
  source.nome_doutor,
  source.data_inicio,
  source.data_fim,
  source.flag_ativo,
  CURRENT_TIMESTAMP(),
  CURRENT_TIMESTAMP()
);

-- Wave 2: pairs observed in consultas not yet in doutor_clinica after wave 1.
MERGE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutor_clinica` AS target
USING (
  SELECT
    ABS(FARM_FINGERPRINT(CONCAT(CAST(c.id_doutor AS STRING), ':', CAST(c.id_clinica AS STRING)))) AS id_doutor_clinica,
    c.id_doutor,
    c.id_clinica,
    d.nome_doutor,
    MIN(c.data_consulta) AS data_inicio,
    NULL AS data_fim,
    COALESCE(d.flag_ativo, TRUE) AS flag_ativo
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_consultas` c
  LEFT JOIN `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutores` d
    USING (id_doutor)
  WHERE c.id_doutor IS NOT NULL
  GROUP BY c.id_doutor, c.id_clinica, d.nome_doutor, d.flag_ativo
) AS source
ON target.id_doutor = source.id_doutor AND target.id_clinica = source.id_clinica
WHEN NOT MATCHED THEN INSERT (
  id_doutor_clinica, id_doutor, id_clinica, nome_doutor, data_inicio, data_fim, flag_ativo, created_at, updated_at
) VALUES (
  source.id_doutor_clinica,
  source.id_doutor,
  source.id_clinica,
  source.nome_doutor,
  source.data_inicio,
  source.data_fim,
  source.flag_ativo,
  CURRENT_TIMESTAMP(),
  CURRENT_TIMESTAMP()
);

-- Verification after backfill: run 017_doctor_clinic_reconciliation.sql next.
