-- VALIDATION TARGET: dataset_dev_trusted_clinica_validacao. Do not run against the primary dataset.
-- Read-only reconciliation after the doctor-clinic backfill (016_doctor_clinic_backfill.sql).
-- Acceptance criteria:
--   * zero duplicate (id_doutor, id_clinica) pairs
--   * zero doctors without at least one doutor_clinica record
--   * zero consultations (with id_doutor filled) without a matching pair in doutor_clinica
--   * no historical record deleted (count must not decrease)

-- 1. Summary counts before and after (compare with 015_doctor_preflight.sql results).
SELECT
  (SELECT COUNT(DISTINCT id_doutor) FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutores`) total_doutores,
  (SELECT COUNT(*) FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutor_clinica`) total_vinculos_pos_backfill,
  (SELECT COUNT(DISTINCT id_doutor) FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutor_clinica`) doutores_com_vinculo_pos_backfill;

-- 2. Duplicate pairs check (must return 0).
SELECT
  COUNT(*) grupos_duplicados,
  IF(COUNT(*) = 0, 'OK - zero pares duplicados', 'FALHA - pares duplicados encontrados') resultado
FROM (
  SELECT id_doutor, id_clinica
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutor_clinica`
  GROUP BY id_doutor, id_clinica HAVING COUNT(*) > 1
);

-- 3. Doctors without any doutor_clinica record (must return 0).
SELECT
  COUNT(*) doutores_sem_vinculo,
  IF(COUNT(*) = 0, 'OK - todos os doutores possuem vinculo', 'FALHA - doutores historicos sem vinculo compativel') resultado
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutores` d
WHERE NOT EXISTS (
  SELECT 1
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutor_clinica` dc
  WHERE dc.id_doutor = d.id_doutor
);

-- 4. Consultations with id_doutor without a matching pair in doutor_clinica (must return 0).
SELECT
  COUNT(*) consultas_sem_vinculo,
  IF(COUNT(*) = 0, 'OK - zero consultas com doutor fora de relacao reconhecida', 'FALHA - consultas com doutor nao reconhecido na ponte') resultado
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_consultas` c
WHERE c.id_doutor IS NOT NULL
  AND NOT EXISTS (
    SELECT 1
    FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutor_clinica` dc
    WHERE dc.id_doutor = c.id_doutor AND dc.id_clinica = c.id_clinica
  );

-- 5. Orphan doutor_clinica records: entries pointing to non-existent doctors or clinics.
SELECT
  COUNT(*) vinculos_orfaos,
  IF(COUNT(*) = 0, 'OK - nenhum vinculo orfao', 'ATENCAO - vinculos orfaos encontrados') resultado
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutor_clinica` dc
WHERE NOT EXISTS (
  SELECT 1
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutores` d
  WHERE d.id_doutor = dc.id_doutor
)
OR NOT EXISTS (
  SELECT 1
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_clinicas` c
  WHERE c.id_clinica = dc.id_clinica
);

-- 6. Consultation quality checks (unchanged; these must match pre-backfill counts).
SELECT
  COUNT(*) total_consultas,
  COUNTIF(id_paciente IS NULL) sem_id_paciente,
  COUNTIF(id_doutor IS NULL) sem_id_doutor,
  COUNTIF(valor_total IS NULL) sem_valor_total
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_consultas`;

-- 7. Financial baseline integrity: total and count of consultations must not change.
--    Compare with 007_financial_baseline.sql output.
SELECT
  id_clinica,
  COALESCE(status, 'SEM_STATUS') status,
  COUNT(*) quantidade_consultas,
  COALESCE(SUM(valor_total), NUMERIC '0') valor_total_consultas
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_consultas`
GROUP BY id_clinica, status
ORDER BY id_clinica, status;
