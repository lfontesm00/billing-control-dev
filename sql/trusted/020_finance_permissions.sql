-- 020_finance_permissions.sql
-- Adiciona permissao de leitura financeira (Fase 4).
-- FINANCE_READ (2015): FULL_ACCESS + FINANCEIRO
--
-- IMPORTANTE: revisar antes de executar; execucao requer autorizacao explicita.

-- 1. Inserir permissao
MERGE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_permissoes` t
USING UNNEST([
  STRUCT(2015 AS id_permissao, 'FINANCE_READ' AS codigo, 'Visualizar resumo financeiro e despesas da clinica' AS descricao)
]) s ON t.codigo = s.codigo
WHEN NOT MATCHED THEN
  INSERT (id_permissao, codigo, descricao)
  VALUES (s.id_permissao, s.codigo, s.descricao);

-- 2. Associar perfis: FULL_ACCESS e FINANCEIRO
MERGE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_perfil_permissoes` t
USING (
  SELECT
    ABS(FARM_FINGERPRINT(CONCAT(p.codigo, ':', x.codigo))) AS id_perfil_permissao,
    p.id_perfil,
    x.id_permissao
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_perfis` p
  JOIN `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_permissoes` x
    ON (p.codigo = 'FULL_ACCESS' AND x.codigo = 'FINANCE_READ')
    OR (p.codigo = 'FINANCEIRO'  AND x.codigo = 'FINANCE_READ')
) s ON t.id_perfil = s.id_perfil AND t.id_permissao = s.id_permissao
WHEN NOT MATCHED THEN
  INSERT (id_perfil_permissao, id_perfil, id_permissao)
  VALUES (s.id_perfil_permissao, s.id_perfil, s.id_permissao);
