-- ADDITIVE MIGRATION. Validation dataset first; never rewrites historical answers.
ALTER TABLE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_anamnese_versoes`
  ADD COLUMN IF NOT EXISTS status_aprovacao STRING,
  ADD COLUMN IF NOT EXISTS id_profissional_aprovador INT64,
  ADD COLUMN IF NOT EXISTS nome_profissional STRING,
  ADD COLUMN IF NOT EXISTS cro_profissional STRING,
  ADD COLUMN IF NOT EXISTS aprovado_em TIMESTAMP;

-- Existing versions remain pending until an authenticated professional reviews them.
UPDATE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_anamnese_versoes`
SET status_aprovacao='PENDENTE_APROVACAO'
WHERE status_aprovacao IS NULL;

MERGE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_permissoes` t
USING (SELECT 2010 id_permissao,'ANAMNESIS_APPROVE' codigo,'Aprovar anamnese como profissional responsável' descricao) s
ON t.codigo=s.codigo
WHEN NOT MATCHED THEN INSERT (id_permissao,codigo,descricao) VALUES(s.id_permissao,s.codigo,s.descricao);

MERGE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_perfil_permissoes` t
USING (
  SELECT ABS(FARM_FINGERPRINT(CONCAT('FULL_ACCESS:',CAST(x.id_permissao AS STRING)))) id_perfil_permissao,p.id_perfil,x.id_permissao
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_perfis` p
  JOIN `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_permissoes` x ON x.codigo='ANAMNESIS_APPROVE'
  WHERE p.codigo='FULL_ACCESS'
) s ON t.id_perfil=s.id_perfil AND t.id_permissao=s.id_permissao
WHEN NOT MATCHED THEN INSERT (id_perfil_permissao,id_perfil,id_permissao) VALUES(s.id_perfil_permissao,s.id_perfil,s.id_permissao);
