-- VALIDATION TARGET: dataset_dev_trusted_clinica_validacao. Do not run against the primary dataset.
-- Read-only preflight for the Doctors domain. Run and inspect every result before the backfill.
-- Expected baseline (2026-09-29): 5 doctors, 1 doutor_clinica record, 201 consultations.

-- 1. Schema snapshot: confirm columns and types before any migration.
SELECT table_name, column_name, data_type, is_nullable, ordinal_position
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name IN (
  'tb_trat_billing_control_doutores',
  'tb_trat_billing_control_doutor_clinica',
  'tb_trat_billing_control_consultas'
)
ORDER BY table_name, ordinal_position;

-- 2. Doctor counts: total rows, distinct IDs, and active flag distribution.
SELECT
  COUNT(*) total_linhas,
  COUNT(DISTINCT id_doutor) ids_unicos,
  COUNTIF(flag_ativo IS TRUE) ativos,
  COUNTIF(flag_ativo IS FALSE OR flag_ativo IS NULL) inativos_ou_sem_flag
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutores`;

-- 3. Doctors with duplicate id_doutor (should be zero).
SELECT
  COUNT(*) grupos_duplicados,
  IF(COUNT(*) = 0, 'OK - nenhum id_doutor duplicado', 'ATENCAO - revisar duplicidades') status
FROM (
  SELECT id_doutor
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutores`
  GROUP BY id_doutor HAVING COUNT(*) > 1
);

-- 4. Existing doutor_clinica records.
SELECT
  COUNT(*) total_vinculos,
  COUNT(DISTINCT id_doutor) doutores_com_vinculo,
  COUNT(DISTINCT id_clinica) clinicas_com_vinculo
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutor_clinica`;

-- 5. Duplicate pairs in doutor_clinica (chave lógica: id_doutor, id_clinica).
SELECT
  COUNT(*) grupos_duplicados,
  IF(COUNT(*) = 0, 'OK - nenhum par duplicado', 'ATENCAO - revisar duplicidades na ponte') status
FROM (
  SELECT id_doutor, id_clinica
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutor_clinica`
  GROUP BY id_doutor, id_clinica HAVING COUNT(*) > 1
);

-- 6. Doctors not yet in doutor_clinica (based on doutores.id_clinica, the historical origin field).
--    These are candidates for the first backfill wave.
SELECT
  d.id_doutor,
  d.nome_doutor,
  d.id_clinica AS id_clinica_historico,
  d.flag_ativo,
  d.percentual_repasse
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutores` d
WHERE NOT EXISTS (
  SELECT 1
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutor_clinica` dc
  WHERE dc.id_doutor = d.id_doutor AND dc.id_clinica = d.id_clinica
)
ORDER BY d.id_doutor;

-- 7. Distinct (id_doutor, id_clinica) pairs found in consultations, not yet in doutor_clinica.
--    These are candidates for the second backfill wave (historical consultation evidence).
SELECT
  c.id_doutor,
  c.id_clinica,
  COUNT(*) consultas_no_par,
  MIN(c.data_consulta) primeira_consulta,
  MAX(c.data_consulta) ultima_consulta
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_consultas` c
WHERE c.id_doutor IS NOT NULL
  AND NOT EXISTS (
    SELECT 1
    FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutor_clinica` dc
    WHERE dc.id_doutor = c.id_doutor AND dc.id_clinica = c.id_clinica
  )
GROUP BY c.id_doutor, c.id_clinica
ORDER BY c.id_doutor, c.id_clinica;

-- 8. Consultations with id_doutor that have no matching pair in doutor_clinica (current state).
SELECT
  COUNT(*) consultas_sem_vinculo_na_ponte,
  COUNT(DISTINCT id_doutor) doutores_distintos_sem_vinculo
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_consultas` c
WHERE c.id_doutor IS NOT NULL
  AND NOT EXISTS (
    SELECT 1
    FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutor_clinica` dc
    WHERE dc.id_doutor = c.id_doutor AND dc.id_clinica = c.id_clinica
  );

-- 9. Consultations with id_doutor pointing to a non-existent doctor (should be zero).
SELECT
  COUNT(*) consultas_com_doutor_inexistente,
  IF(COUNT(*) = 0, 'OK - todos os id_doutor preenchidos existem', 'ATENCAO - id_doutor orfao em consultas') status
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_consultas` c
WHERE c.id_doutor IS NOT NULL
  AND NOT EXISTS (
    SELECT 1
    FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutores` d
    WHERE d.id_doutor = c.id_doutor
  );

-- 10. Consultation quality summary: id_paciente and id_doutor fill rates.
SELECT
  COUNT(*) total_consultas,
  COUNTIF(id_paciente IS NOT NULL) com_id_paciente,
  COUNTIF(id_doutor IS NOT NULL) com_id_doutor,
  COUNTIF(valor_total IS NOT NULL) com_valor_total,
  COUNTIF(id_paciente IS NULL) sem_id_paciente,
  COUNTIF(id_doutor IS NULL) sem_id_doutor,
  COUNTIF(valor_total IS NULL) sem_valor_total
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_consultas`;

-- 11. Impact preview: how many new doutor_clinica rows would the backfill insert?
--     Wave 1: from doutores.id_clinica
WITH wave1 AS (
  SELECT d.id_doutor, d.id_clinica, 'WAVE1_DOUTORES_ID_CLINICA' AS origem
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutores` d
  WHERE NOT EXISTS (
    SELECT 1
    FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutor_clinica` dc
    WHERE dc.id_doutor = d.id_doutor AND dc.id_clinica = d.id_clinica
  )
),
-- Wave 2: from consultas, excluding pairs already covered by wave1
wave2 AS (
  SELECT DISTINCT c.id_doutor, c.id_clinica, 'WAVE2_CONSULTAS_HISTORICAS' AS origem
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_consultas` c
  WHERE c.id_doutor IS NOT NULL
    AND NOT EXISTS (
      SELECT 1
      FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutor_clinica` dc
      WHERE dc.id_doutor = c.id_doutor AND dc.id_clinica = c.id_clinica
    )
    AND NOT EXISTS (SELECT 1 FROM wave1 w WHERE w.id_doutor = c.id_doutor AND w.id_clinica = c.id_clinica)
)
SELECT origem, COUNT(*) novos_vinculos_a_inserir
FROM (SELECT origem FROM wave1 UNION ALL SELECT origem FROM wave2)
GROUP BY origem
ORDER BY origem;

-- 12. Consultations that would remain unlinked even after the full backfill (orphan consultations).
--     After backfill both waves should cover all id_doutor IS NOT NULL consultations.
WITH all_new_pairs AS (
  SELECT d.id_doutor, d.id_clinica
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutores` d
  UNION DISTINCT
  SELECT c.id_doutor, c.id_clinica
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_consultas` c
  WHERE c.id_doutor IS NOT NULL
),
covered_pairs AS (
  SELECT id_doutor, id_clinica FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutor_clinica`
  UNION DISTINCT
  SELECT id_doutor, id_clinica FROM all_new_pairs
)
SELECT
  COUNT(*) consultas_ainda_sem_vinculo_pos_backfill
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_consultas` c
WHERE c.id_doutor IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM covered_pairs cp WHERE cp.id_doutor = c.id_doutor AND cp.id_clinica = c.id_clinica
  );
