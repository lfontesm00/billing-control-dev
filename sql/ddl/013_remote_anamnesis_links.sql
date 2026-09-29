-- ADDITIVE MIGRATION. Run first on dataset_dev_trusted_clinica_validacao.
-- It does not rewrite historical patients or anamneses.
ALTER TABLE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_sessoes_paciente`
  ADD COLUMN IF NOT EXISTS tipo_sessao STRING,
  ADD COLUMN IF NOT EXISTS id_formulario INT64,
  ADD COLUMN IF NOT EXISTS versao_formulario INT64,
  ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP,
  ADD COLUMN IF NOT EXISTS papel_confirmante STRING,
  ADD COLUMN IF NOT EXISTS tentativas_verificacao INT64,
  ADD COLUMN IF NOT EXISTS bloqueada_em TIMESTAMP,
  ADD COLUMN IF NOT EXISTS canal_compartilhamento STRING,
  ADD COLUMN IF NOT EXISTS key_version STRING;

UPDATE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_sessoes_paciente`
SET tipo_sessao=COALESCE(tipo_sessao,'LOCAL'),tentativas_verificacao=COALESCE(tentativas_verificacao,0)
WHERE tipo_sessao IS NULL OR tentativas_verificacao IS NULL;

ALTER TABLE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_anamnese_versoes`
  ADD COLUMN IF NOT EXISTS id_sessao_origem INT64,
  ADD COLUMN IF NOT EXISTS id_evidencia INT64,
  ADD COLUMN IF NOT EXISTS content_hmac STRING,
  ADD COLUMN IF NOT EXISTS key_version STRING,
  ADD COLUMN IF NOT EXISTS papel_confirmante STRING;

CREATE TABLE IF NOT EXISTS `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_anamnesis_evidence` (
  id_evidencia INT64 NOT NULL,
  id_sessao INT64 NOT NULL,
  id_clinica INT64 NOT NULL,
  id_paciente INT64 NOT NULL,
  id_formulario INT64,
  event_type STRING NOT NULL,
  request_id STRING NOT NULL,
  ip_hmac STRING NOT NULL,
  user_agent STRING,
  user_agent_hash STRING NOT NULL,
  content_hmac STRING,
  key_version STRING NOT NULL,
  origem_registro STRING NOT NULL,
  created_at TIMESTAMP NOT NULL
) PARTITION BY DATE(created_at) CLUSTER BY id_clinica,id_paciente,id_sessao;

SELECT table_name,column_name,data_type
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name IN ('bc_sessoes_paciente','bc_anamnese_versoes','bc_anamnesis_evidence')
ORDER BY table_name,ordinal_position;
