-- VALIDATION TARGET ONLY. Returns all technical forms to their safe draft state.
DECLARE form_ids ARRAY<INT64> DEFAULT [3001,3002];

ASSERT (
  SELECT COUNT(*) = ARRAY_LENGTH(form_ids)
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_formularios`
  WHERE id_formulario IN UNNEST(form_ids)
    AND status IN ('RASCUNHO', 'PUBLICADO_TESTE')
    AND validado_clinicamente = FALSE
) AS 'Os formulários técnicos não existem ou possuem estado incompatível; nenhuma alteração foi realizada';

UPDATE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_formularios`
SET
  status = 'RASCUNHO',
  validado_clinicamente = FALSE,
  published_at = NULL
WHERE id_formulario IN UNNEST(form_ids)
  AND validado_clinicamente = FALSE;

SELECT id_formulario,nome,versao,status,validado_clinicamente,published_at
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_formularios`
WHERE id_formulario IN UNNEST(form_ids)
ORDER BY id_formulario;
