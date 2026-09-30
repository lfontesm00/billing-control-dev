-- VALIDATION TARGET: dataset_dev_trusted_clinica_validacao. Do not run against the primary dataset.
-- Add DOCTOR_READ, DOCTOR_MANAGE, and DOCTOR_CLINIC_MANAGE permissions and assign them to profiles.
--
-- Permission IDs (follow the 2001-2010 range in 002_seed_mvp.sql):
--   2011 DOCTOR_READ          — list and view doctors in a clinic
--   2012 DOCTOR_MANAGE        — edit doctor profiles (name, CRO, specialty, repasse)
--   2013 DOCTOR_CLINIC_MANAGE — manage doctor-clinic links (add/deactivate)
--
-- Profile assignments:
--   FULL_ACCESS (1001): DOCTOR_READ + DOCTOR_MANAGE + DOCTOR_CLINIC_MANAGE
--   RECEPCAO    (1002): DOCTOR_READ only
--   FINANCEIRO  (1003): none (financial profile does not need clinical doctor access)
--
-- Both MERGEs are idempotent: re-running is safe.

MERGE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_permissoes` t
USING UNNEST([
  STRUCT(2011 AS id_permissao, 'DOCTOR_READ'          AS codigo, 'Consultar doutores da clínica'             AS descricao),
  (2012,                       'DOCTOR_MANAGE',                  'Editar cadastro de doutores'),
  (2013,                       'DOCTOR_CLINIC_MANAGE',           'Gerenciar vínculos doutor–clínica')
]) s ON t.codigo = s.codigo
WHEN NOT MATCHED THEN
  INSERT (id_permissao, codigo, descricao)
  VALUES (s.id_permissao, s.codigo, s.descricao);

MERGE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_perfil_permissoes` t
USING (
  SELECT
    ABS(FARM_FINGERPRINT(CONCAT(p.codigo, ':', x.codigo))) AS id_perfil_permissao,
    p.id_perfil,
    x.id_permissao
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_perfis` p
  JOIN `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_permissoes` x
    ON (p.codigo = 'FULL_ACCESS' AND x.codigo IN ('DOCTOR_READ', 'DOCTOR_MANAGE', 'DOCTOR_CLINIC_MANAGE'))
    OR (p.codigo = 'RECEPCAO'    AND x.codigo IN ('DOCTOR_READ'))
) s ON t.id_perfil = s.id_perfil AND t.id_permissao = s.id_permissao
WHEN NOT MATCHED THEN
  INSERT (id_perfil_permissao, id_perfil, id_permissao)
  VALUES (s.id_perfil_permissao, s.id_perfil, s.id_permissao);
