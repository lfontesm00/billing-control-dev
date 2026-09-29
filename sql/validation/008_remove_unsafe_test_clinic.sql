-- VALIDATION TARGET ONLY: removes the fictitious clinic created before IDs were
-- constrained to JavaScript's safe integer range. Never run on the primary dataset.
DECLARE clinic_id INT64 DEFAULT 2033852014496372383;
DECLARE expected_document STRING DEFAULT '11222333000181';

ASSERT (
  SELECT COUNT(*) = 1
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_clinicas`
  WHERE id_clinica = clinic_id
    AND REGEXP_REPLACE(cnpj_cpf, r'\D', '') = expected_document
    AND origem_registro = 'WEB_APP_V1'
) AS 'A clínica alvo não existe ou não corresponde ao registro fictício WEB_APP_V1';

ASSERT (
  SELECT COUNT(*) = 0
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_paciente_clinica`
  WHERE id_clinica = clinic_id
) AS 'A clínica possui vínculos de pacientes e não pode ser removida por este script';

ASSERT (
  SELECT COUNT(*) = 0
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_consultas`
  WHERE id_clinica = clinic_id
) AS 'A clínica possui consultas e não pode ser removida por este script';

ASSERT (
  SELECT COUNT(*) = 0
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_despesas`
  WHERE id_clinica = clinic_id
) AS 'A clínica possui despesas e não pode ser removida por este script';

ASSERT (
  SELECT COUNT(*) = 0
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_doutor_clinica`
  WHERE id_clinica = clinic_id
) AS 'A clínica possui vínculos de doutores e não pode ser removida por este script';

BEGIN TRANSACTION;

DELETE FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_usuario_clinicas`
WHERE id_clinica = clinic_id;

DELETE FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_organizacao_clinicas`
WHERE id_clinica = clinic_id;

DELETE FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_auditoria`
WHERE id_clinica = clinic_id
   OR (entidade = 'CLINICA' AND id_entidade = clinic_id);

DELETE FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_clinicas`
WHERE id_clinica = clinic_id
  AND REGEXP_REPLACE(cnpj_cpf, r'\D', '') = expected_document
  AND origem_registro = 'WEB_APP_V1';

COMMIT TRANSACTION;

SELECT
  clinic_id AS id_removido,
  COUNT(*) AS registros_restantes
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_clinicas`
WHERE id_clinica = clinic_id;
