-- VALIDATION TARGET: dataset_dev_trusted_clinica_validacao. Do not run against the primary dataset.
-- Read-only reconciliation after deployment to the validation dataset.
WITH patient_latest AS (
  SELECT *
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_pacientes`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id_paciente ORDER BY updated_at DESC,created_at DESC)=1
), anamnesis_latest AS (
  SELECT *
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_anamnese_pacientes`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id_anamnese ORDER BY updated_at DESC,created_at DESC)=1
)
SELECT
  (SELECT COUNT(*) FROM patient_latest) pacientes_atuais,
  (SELECT COUNT(*) FROM anamnesis_latest) anamneses_atuais,
  (SELECT COUNT(*) FROM patient_latest)>=219 AS base_minima_pacientes_preservada,
  (SELECT COUNT(*) FROM anamnesis_latest)>=219 AS base_minima_anamneses_preservada;

SELECT p.id_paciente,p.fk_anamnese_paciente
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_pacientes` p
LEFT JOIN `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_anamnese_pacientes` a
  ON a.fk_anamnese_paciente=p.fk_anamnese_paciente OR a.id_anamnese=p.fk_anamnese_paciente OR a.id_paciente=p.id_paciente
WHERE p.fk_anamnese_paciente IS NOT NULL AND a.id_anamnese IS NULL;

SELECT id_clinica,id_paciente,COUNT(*) quantidade
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_paciente_clinica`
GROUP BY id_clinica,id_paciente HAVING COUNT(*)>1 ORDER BY quantidade DESC;
