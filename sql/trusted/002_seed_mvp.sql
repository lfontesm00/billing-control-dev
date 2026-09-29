-- VALIDATION TARGET: dataset_dev_trusted_clinica_validacao. Do not run against the primary dataset.
-- Stable seed IDs make the script idempotent across environments.
MERGE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_perfis` t
USING UNNEST([
  STRUCT(1001 AS id_perfil,'FULL_ACCESS' AS codigo,'Acesso completo' AS nome,TRUE AS ativo),
  (1002,'RECEPCAO','Recepção',TRUE), (1003,'FINANCEIRO','Financeiro',TRUE)
]) s ON t.codigo=s.codigo
WHEN NOT MATCHED THEN
  INSERT (id_perfil,codigo,nome,ativo)
  VALUES (s.id_perfil,s.codigo,s.nome,s.ativo);

MERGE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_permissoes` t
USING UNNEST([
  STRUCT(2001 AS id_permissao,'CLINIC_MANAGE' AS codigo,'Gerenciar clínicas' AS descricao),
  (2002,'USER_MANAGE','Gerenciar usuários'), (2003,'PATIENT_READ','Consultar pacientes'),
  (2004,'PATIENT_WRITE','Cadastrar e alterar pacientes'), (2005,'ANAMNESIS_READ','Consultar anamnese'),
  (2006,'ANAMNESIS_WRITE','Preencher anamnese'), (2007,'PATIENT_MODE','Iniciar modo paciente'),
  (2008,'FINANCIAL_READ','Consultar financeiro'), (2009,'FINANCIAL_WRITE','Alterar financeiro'),
  (2010,'ANAMNESIS_APPROVE','Aprovar anamnese como profissional responsável')
]) s ON t.codigo=s.codigo
WHEN NOT MATCHED THEN
  INSERT (id_permissao,codigo,descricao)
  VALUES (s.id_permissao,s.codigo,s.descricao);

MERGE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_perfil_permissoes` t
USING (
  SELECT ABS(FARM_FINGERPRINT(CONCAT(p.codigo,':',x.codigo))) id_perfil_permissao,p.id_perfil,x.id_permissao
  FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_perfis` p
  JOIN `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_permissoes` x
    ON p.codigo='FULL_ACCESS'
    OR (p.codigo='RECEPCAO' AND x.codigo IN ('PATIENT_READ','PATIENT_WRITE','ANAMNESIS_READ','ANAMNESIS_WRITE','PATIENT_MODE'))
    OR (p.codigo='FINANCEIRO' AND x.codigo IN ('FINANCIAL_READ','FINANCIAL_WRITE'))
) s ON t.id_perfil=s.id_perfil AND t.id_permissao=s.id_permissao
WHEN NOT MATCHED THEN
  INSERT (id_perfil_permissao,id_perfil,id_permissao)
  VALUES (s.id_perfil_permissao,s.id_perfil,s.id_permissao);

-- Demonstration form: intentionally RASCUNHO/not validated. A dentist must review it and publish it.
MERGE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_formularios` t
USING (SELECT 3001 id_formulario,CAST(NULL AS INT64) id_clinica,'Anamnese inicial demonstrativa' nome,1 versao,
  'RASCUNHO' status,FALSE validado_clinicamente,'demo-v1' termos_versao,
  'Confirmo que as informações fornecidas são verdadeiras.' termos_texto,CURRENT_TIMESTAMP() created_at,CAST(NULL AS TIMESTAMP) published_at) s
ON t.id_formulario=s.id_formulario
WHEN NOT MATCHED THEN
  INSERT (id_formulario,id_clinica,nome,versao,status,validado_clinicamente,termos_versao,termos_texto,created_at,published_at)
  VALUES (s.id_formulario,s.id_clinica,s.nome,s.versao,s.status,s.validado_clinicamente,s.termos_versao,s.termos_texto,s.created_at,s.published_at);

MERGE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_perguntas` t
USING UNNEST([
  STRUCT(3101 AS id_pergunta,3001 AS id_formulario,'ALERGIA' AS codigo,'Possui alergia?' AS texto,'BOOLEAN' AS tipo,TRUE AS obrigatoria,1 AS ordem,CAST(NULL AS INT64) AS parent_question_id,CAST(NULL AS STRING) AS show_when_value,'ALERGIA' AS alert_code,'ALERGIA INFORMADA' AS alert_template,CAST([] AS ARRAY<STRING>) AS options),
  (3102,3001,'ALERGIA_QUAL','Qual alergia?','TEXT',TRUE,2,3101,'true',NULL,NULL,[]),
  (3103,3001,'HIPERTENSAO','Possui hipertensão?','BOOLEAN',TRUE,3,NULL,NULL,'HIPERTENSAO','HIPERTENSÃO',[]),
  (3104,3001,'ANTICOAGULANTE','Usa anticoagulante?','BOOLEAN',TRUE,4,NULL,NULL,'ANTICOAGULANTE','USO DE ANTICOAGULANTE',[])
]) s ON t.id_pergunta=s.id_pergunta
WHEN NOT MATCHED THEN
  INSERT (id_pergunta,id_formulario,codigo,texto,tipo,obrigatoria,ordem,parent_question_id,show_when_value,alert_code,alert_template,options)
  VALUES (s.id_pergunta,s.id_formulario,s.codigo,s.texto,s.tipo,s.obrigatoria,s.ordem,s.parent_question_id,s.show_when_value,s.alert_code,s.alert_template,s.options);
