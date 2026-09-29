-- VALIDATION TARGET: dataset_dev_trusted_clinica_validacao. Do not run against the primary dataset.
-- Read-only financial baseline. Export the results before and after validation.
-- Baseline captured on 2026-08-21:
-- consultas: FINALIZADA=201 / 46555.50 / 2026-01-07..2026-07-08
-- itens: 224 rows / 187 consultations / 60705.50
-- despesas: NOK=1 / 62.75; OK=59 / 9032.63
SELECT
  id_clinica,
  COALESCE(status,'SEM_STATUS') status,
  COUNT(*) quantidade_consultas,
  COALESCE(SUM(valor_total),NUMERIC '0') valor_total_consultas,
  MIN(data_consulta) primeira_consulta,
  MAX(data_consulta) ultima_consulta
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_consultas`
GROUP BY id_clinica,status
ORDER BY id_clinica,status;

SELECT
  id_clinica,
  COUNT(*) quantidade_itens,
  COUNT(DISTINCT id_consulta) consultas_com_procedimentos,
  COALESCE(SUM(valor_consulta),NUMERIC '0') valor_total_itens
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_consulta_procedimentos`
GROUP BY id_clinica
ORDER BY id_clinica;

SELECT
  id_clinica,
  COALESCE(status,'SEM_STATUS') status,
  COUNT(*) quantidade_despesas,
  COALESCE(SUM(valor_despesa),NUMERIC '0') valor_total_despesas,
  MIN(data_pagamento) primeiro_pagamento,
  MAX(data_pagamento) ultimo_pagamento
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_despesas`
GROUP BY id_clinica,status
ORDER BY id_clinica,status;

-- Automated comparison with the captured baseline. This MVP does not write financial tables.
WITH expected AS (
  SELECT 1 id_clinica,'FINALIZADA' status,201 quantidade,NUMERIC '46555.50' valor,DATE '2026-01-07' primeira_data,DATE '2026-07-08' ultima_data
), actual AS (
  SELECT id_clinica,COALESCE(status,'SEM_STATUS') status,COUNT(*) quantidade,COALESCE(SUM(valor_total),NUMERIC '0') valor,MIN(data_consulta) primeira_data,MAX(data_consulta) ultima_data
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_consultas`
  GROUP BY id_clinica,status
)
SELECT
  COALESCE(e.id_clinica,a.id_clinica) id_clinica,
  COALESCE(e.status,a.status) status,
  IF(TO_JSON_STRING(e)=TO_JSON_STRING(a),'OK','DIVERGENTE') resultado,
  e AS esperado,
  a AS atual
FROM expected e FULL OUTER JOIN actual a USING(id_clinica,status);

WITH expected AS (
  SELECT 1 id_clinica,224 quantidade_itens,187 consultas_com_procedimentos,NUMERIC '60705.50' valor_total_itens
), actual AS (
  SELECT id_clinica,COUNT(*) quantidade_itens,COUNT(DISTINCT id_consulta) consultas_com_procedimentos,COALESCE(SUM(valor_consulta),NUMERIC '0') valor_total_itens
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_consulta_procedimentos`
  GROUP BY id_clinica
)
SELECT
  COALESCE(e.id_clinica,a.id_clinica) id_clinica,
  IF(TO_JSON_STRING(e)=TO_JSON_STRING(a),'OK','DIVERGENTE') resultado,
  e AS esperado,
  a AS atual
FROM expected e FULL OUTER JOIN actual a USING(id_clinica);

WITH expected AS (
  SELECT 1 id_clinica,'NOK' status,1 quantidade,NUMERIC '62.75' valor,DATE '2026-01-30' primeira_data,DATE '2026-01-30' ultima_data
  UNION ALL SELECT 1,'OK',59,NUMERIC '9032.63',DATE '2026-01-08',DATE '2026-07-25'
), actual AS (
  SELECT id_clinica,COALESCE(status,'SEM_STATUS') status,COUNT(*) quantidade,COALESCE(SUM(valor_despesa),NUMERIC '0') valor,MIN(data_pagamento) primeira_data,MAX(data_pagamento) ultima_data
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_despesas`
  GROUP BY id_clinica,status
)
SELECT
  COALESCE(e.id_clinica,a.id_clinica) id_clinica,
  COALESCE(e.status,a.status) status,
  IF(TO_JSON_STRING(e)=TO_JSON_STRING(a),'OK','DIVERGENTE') resultado,
  e AS esperado,
  a AS atual
FROM expected e FULL OUTER JOIN actual a USING(id_clinica,status);
