-- VALIDATION TARGET: dataset_dev_trusted_clinica_validacao. Do not run against the primary dataset.
-- Read-only preflight. Run and inspect every result before applying migrations.
SELECT table_name, column_name, data_type, is_nullable, ordinal_position
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name IN (
  'tb_trat_billing_control_clinicas',
  'tb_trat_billing_control_pacientes',
  'tb_trat_billing_control_paciente_clinica',
  'tb_trat_billing_control_anamnese_pacientes'
)
ORDER BY table_name, ordinal_position;

SELECT 'pacientes' entidade, COUNT(*) linhas, COUNT(DISTINCT id_paciente) ids_unicos
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_pacientes`
UNION ALL
SELECT 'anamneses', COUNT(*), COUNT(DISTINCT id_anamnese)
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_anamnese_pacientes`;

SELECT
  COUNT(*) grupos_duplicados,
  IF(COUNT(*)=0,'OK - nenhum id_paciente duplicado','ATENCAO - revisar duplicidades') status
FROM (
  SELECT id_paciente
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_pacientes`
  GROUP BY id_paciente HAVING COUNT(*) > 1
);

SELECT
  COUNT(*) vinculos_orfaos,
  IF(COUNT(*)=0,'OK - nenhum vinculo orfao','ATENCAO - revisar vinculos') status
FROM (
  SELECT pc.id_paciente,pc.id_clinica
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_paciente_clinica` pc
  LEFT JOIN `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_pacientes` p USING (id_paciente)
  LEFT JOIN `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_clinicas` c USING (id_clinica)
  WHERE p.id_paciente IS NULL OR c.id_clinica IS NULL
);

SELECT
  COUNT(*) grupos_duplicados,
  IF(COUNT(*)=0,'OK - nenhum id_anamnese duplicado','ATENCAO - revisar duplicidades') status
FROM (
  SELECT id_anamnese
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_anamnese_pacientes`
  GROUP BY id_anamnese HAVING COUNT(*) > 1
);

SELECT
  COUNT(*) referencias_orfas,
  IF(COUNT(*)=0,'OK - referencias de anamnese consistentes','ATENCAO - referencia sem correspondencia por fk ou id_anamnese') status
FROM (
  SELECT p.id_paciente,p.fk_anamnese_paciente
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_pacientes` p
  WHERE p.fk_anamnese_paciente IS NOT NULL
    AND NOT EXISTS (
      SELECT 1
      FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_anamnese_pacientes` a
      WHERE a.fk_anamnese_paciente=p.fk_anamnese_paciente
         OR a.id_anamnese=p.fk_anamnese_paciente
         OR a.id_paciente=p.id_paciente
    )
);

SELECT
  p.id_paciente,
  p.fk_anamnese_paciente,
  EXISTS (
    SELECT 1 FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_anamnese_pacientes` a
    WHERE a.fk_anamnese_paciente=p.fk_anamnese_paciente
  ) match_por_fk,
  EXISTS (
    SELECT 1 FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_anamnese_pacientes` a
    WHERE a.id_anamnese=p.fk_anamnese_paciente
  ) match_por_id_anamnese,
  EXISTS (
    SELECT 1 FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_anamnese_pacientes` a
    WHERE a.id_paciente=p.id_paciente
  ) match_por_id_paciente,
  CASE
    WHEN EXISTS (SELECT 1 FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_anamnese_pacientes` a WHERE a.fk_anamnese_paciente=p.fk_anamnese_paciente) THEN 'FK_ANAMNESE_PACIENTE'
    WHEN EXISTS (SELECT 1 FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_anamnese_pacientes` a WHERE a.id_anamnese=p.fk_anamnese_paciente) THEN 'ID_ANAMNESE'
    WHEN EXISTS (SELECT 1 FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_anamnese_pacientes` a WHERE a.id_paciente=p.id_paciente) THEN 'ID_PACIENTE'
    ELSE 'SEM_CORRESPONDENCIA'
  END tipo_relacionamento
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_pacientes` p
WHERE p.fk_anamnese_paciente IS NOT NULL
ORDER BY tipo_relacionamento,id_paciente;
