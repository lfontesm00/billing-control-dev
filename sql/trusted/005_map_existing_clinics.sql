-- VALIDATION TARGET: dataset_dev_trusted_clinica_validacao. Do not run against the primary dataset.
-- Run only after /api/v1/setup has created the owner organization.
-- Replace both zeros with the IDs returned by setup/query. The script is idempotent.
DECLARE organization_id INT64 DEFAULT 3965055167959469407;
DECLARE administrator_user_id INT64 DEFAULT 2842519271168443175;
ASSERT organization_id != 0 AS 'Defina organization_id antes de executar';
ASSERT administrator_user_id != 0 AS 'Defina administrator_user_id antes de executar';
ASSERT (
  SELECT COUNT(*) = 1
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_usuarios` u
  JOIN `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_usuario_perfis` up USING (id_usuario)
  JOIN `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_perfis` p USING (id_perfil)
  WHERE u.id_usuario=administrator_user_id
    AND u.id_organizacao=organization_id
    AND u.ativo
    AND p.codigo='FULL_ACCESS'
) AS 'O usuário deve estar ativo, pertencer à organização e possuir FULL_ACCESS';
ASSERT (
  SELECT COUNT(DISTINCT id_clinica)
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_clinicas`
) <= 3 AS 'A organização MVP pode possuir no máximo três clínicas';

MERGE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_organizacao_clinicas` target
USING (
  SELECT DISTINCT
    ABS(FARM_FINGERPRINT(CONCAT(GENERATE_UUID(), ':', CAST(organization_id AS STRING), ':', CAST(id_clinica AS STRING)))) id_organizacao_clinica,
    organization_id id_organizacao,
    id_clinica
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_clinicas`
) source
ON target.id_organizacao=source.id_organizacao AND target.id_clinica=source.id_clinica
WHEN MATCHED THEN
  UPDATE SET ativo=TRUE,updated_at=CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN
  INSERT (id_organizacao_clinica,id_organizacao,id_clinica,ativo,created_at,updated_at)
  VALUES (source.id_organizacao_clinica,source.id_organizacao,source.id_clinica,TRUE,CURRENT_TIMESTAMP(),CURRENT_TIMESTAMP());

MERGE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_usuario_clinicas` target
USING (
  SELECT DISTINCT
    ABS(FARM_FINGERPRINT(CONCAT(GENERATE_UUID(), ':', CAST(administrator_user_id AS STRING), ':', CAST(id_clinica AS STRING)))) id_usuario_clinica,
    administrator_user_id id_usuario,
    id_clinica
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_clinicas`
) source
ON target.id_usuario=source.id_usuario AND target.id_clinica=source.id_clinica
WHEN MATCHED THEN
  UPDATE SET ativo=TRUE,updated_at=CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN
  INSERT (id_usuario_clinica,id_usuario,id_clinica,ativo,created_at,updated_at)
  VALUES (source.id_usuario_clinica,source.id_usuario,source.id_clinica,TRUE,CURRENT_TIMESTAMP(),CURRENT_TIMESTAMP());
