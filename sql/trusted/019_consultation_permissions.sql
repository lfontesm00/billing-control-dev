-- 019_consultation_permissions.sql
-- Adiciona permissões de leitura de consultas (Fase 3 — modo leitura).
-- CONSULTATION_READ (2014): FULL_ACCESS + RECEPCAO
--
-- IMPORTANTE: revisar antes de executar; execução requer autorização explícita.

DECLARE dataset STRING DEFAULT 'datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao';

-- 1. Inserir permissão
MERGE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_permissoes` t
USING UNNEST([
  STRUCT(2014 AS id_permissao, 'CONSULTATION_READ' AS codigo, 'Consultar consultas e procedimentos da clínica' AS descricao)
]) s ON t.codigo = s.codigo
WHEN NOT MATCHED THEN
  INSERT (id_permissao, codigo, descricao)
  VALUES (s.id_permissao, s.codigo, s.descricao);

-- 2. Associar perfis
MERGE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_perfil_permissoes` t
USING (
  SELECT
    ABS(FARM_FINGERPRINT(CONCAT(p.codigo, ':', x.codigo))) AS id_perfil_permissao,
    p.id_perfil,
    x.id_permissao
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_perfis` p
  JOIN `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_permissoes` x
    ON (p.codigo = 'FULL_ACCESS' AND x.codigo IN ('CONSULTATION_READ'))
    OR (p.codigo = 'RECEPCAO'    AND x.codigo IN ('CONSULTATION_READ'))
) s ON t.id_perfil = s.id_perfil AND t.id_permissao = s.id_permissao
WHEN NOT MATCHED THEN
  INSERT (id_perfil_permissao, id_perfil, id_permissao)
  VALUES (s.id_perfil_permissao, s.id_perfil, s.id_permissao);
