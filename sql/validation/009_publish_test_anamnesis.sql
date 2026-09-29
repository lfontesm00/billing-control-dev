-- VALIDATION TARGET ONLY. Publishes form 3001 for technical testing without
-- declaring clinical approval. Requires ALLOW_UNVALIDATED_TEST_FORMS=True in API.
DECLARE form_id INT64 DEFAULT 3001;

ASSERT (
  SELECT COUNT(*) = 1
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_formularios`
  WHERE id_formulario = form_id
    AND status IN ('RASCUNHO', 'PUBLICADO_TESTE')
    AND validado_clinicamente = FALSE
) AS 'O formulário técnico não existe, já foi aprovado clinicamente ou possui status incompatível';

UPDATE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_formularios`
SET
  status = 'PUBLICADO_TESTE',
  validado_clinicamente = FALSE,
  published_at = CURRENT_TIMESTAMP()
WHERE id_formulario = form_id
  AND validado_clinicamente = FALSE;

SELECT id_formulario,nome,versao,status,validado_clinicamente,published_at
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_formularios`
WHERE id_formulario = form_id;
