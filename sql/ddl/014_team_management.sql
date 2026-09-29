-- ADDITIVE MIGRATION. Run on the validation dataset before testing team management.
ALTER TABLE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_usuarios`
  ADD COLUMN IF NOT EXISTS troca_senha_obrigatoria BOOL,
  ADD COLUMN IF NOT EXISTS alterado_administrativamente_em TIMESTAMP,
  ADD COLUMN IF NOT EXISTS alterado_por_id_usuario INT64;

UPDATE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_usuarios`
SET troca_senha_obrigatoria=FALSE
WHERE troca_senha_obrigatoria IS NULL;
