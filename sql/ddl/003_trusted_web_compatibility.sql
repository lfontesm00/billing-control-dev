-- VALIDATION TARGET: dataset_dev_trusted_clinica_validacao. Do not run against the primary dataset.
-- Additive compatibility migration for API writes to the historical Trusted tables.
-- This script never drops, truncates, renames, or rewrites historical data.

ALTER TABLE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_clinicas`
  ADD COLUMN IF NOT EXISTS telefone STRING,
  ADD COLUMN IF NOT EXISTS responsavel STRING,
  ADD COLUMN IF NOT EXISTS cro_responsavel STRING,
  ADD COLUMN IF NOT EXISTS origem_registro STRING;

ALTER TABLE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_pacientes`
  ADD COLUMN IF NOT EXISTS plano_odontologico STRING,
  ADD COLUMN IF NOT EXISTS origem_registro STRING,
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMP,
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;

ALTER TABLE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_paciente_clinica`
  ADD COLUMN IF NOT EXISTS origem_registro STRING,
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMP,
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;

ALTER TABLE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_anamnese_pacientes`
  ADD COLUMN IF NOT EXISTS id_paciente INT64,
  ADD COLUMN IF NOT EXISTS id_clinica INT64,
  ADD COLUMN IF NOT EXISTS id_formulario INT64,
  ADD COLUMN IF NOT EXISTS respostas_json JSON,
  ADD COLUMN IF NOT EXISTS aceite_nome STRING,
  ADD COLUMN IF NOT EXISTS aceite_cpf STRING,
  ADD COLUMN IF NOT EXISTS termos_versao STRING,
  ADD COLUMN IF NOT EXISTS aceito_em TIMESTAMP,
  ADD COLUMN IF NOT EXISTS origem_registro STRING,
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMP,
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;
