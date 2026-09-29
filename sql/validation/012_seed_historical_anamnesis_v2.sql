-- VALIDATION TARGET ONLY. Creates a new immutable form definition; does not edit form 3001 or 219 legacy anamneses.
MERGE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_formularios` t
USING (SELECT 3002 id_formulario,CAST(NULL AS INT64) id_clinica,'Anamnese odontológica baseada no formulário histórico' nome,2 versao,
  'PUBLICADO_TESTE' status,FALSE validado_clinicamente,'historico-v2-teste' termos_versao,
  'Declaro que as informações fornecidas são verdadeiras e autorizo sua revisão pelo profissional responsável.' termos_texto,
  CURRENT_TIMESTAMP() created_at,CURRENT_TIMESTAMP() published_at) s
ON t.id_formulario=s.id_formulario
WHEN NOT MATCHED THEN INSERT (id_formulario,id_clinica,nome,versao,status,validado_clinicamente,termos_versao,termos_texto,created_at,published_at)
VALUES(s.id_formulario,s.id_clinica,s.nome,s.versao,s.status,s.validado_clinicamente,s.termos_versao,s.termos_texto,s.created_at,s.published_at);

MERGE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_perguntas` t
USING UNNEST([
  STRUCT(3201 AS id_pergunta,3002 AS id_formulario,'CIRURGIA' AS codigo,'Já realizou alguma cirurgia?' AS texto,'BOOLEAN' AS tipo,TRUE AS obrigatoria,1 AS ordem,CAST(NULL AS INT64) AS parent_question_id,CAST(NULL AS STRING) AS show_when_value,CAST(NULL AS STRING) AS alert_code,CAST(NULL AS STRING) AS alert_template,CAST([] AS ARRAY<STRING>) AS options),
  (3202,3002,'CIRURGIA_DETALHE','Qual cirurgia e quando?','TEXT',TRUE,2,3201,'true',NULL,NULL,[]),
  (3203,3002,'TRATAMENTO_MEDICO','Está ou esteve recentemente em tratamento médico?','BOOLEAN',TRUE,3,NULL,NULL,NULL,NULL,[]),
  (3204,3002,'TRATAMENTO_MEDICO_DETALHE','Informe o tratamento e o profissional responsável.','TEXT',TRUE,4,3203,'true',NULL,NULL,[]),
  (3205,3002,'MEDICAMENTO_CONTINUO','Faz uso contínuo de algum medicamento?','BOOLEAN',TRUE,5,NULL,NULL,'MEDICAMENTO_CONTINUO','USO CONTÍNUO DE MEDICAMENTO',[]),
  (3206,3002,'MEDICAMENTO_CONTINUO_DETALHE','Informe os medicamentos, doses e horários.','TEXT',TRUE,6,3205,'true',NULL,NULL,[]),
  (3207,3002,'ALERGIA','Possui alergia a medicamento, anestésico, látex ou outra substância?','BOOLEAN',TRUE,7,NULL,NULL,'ALERGIA','ALERGIA INFORMADA',[]),
  (3208,3002,'ALERGIA_QUAL','Descreva todas as alergias conhecidas.','TEXT',TRUE,8,3207,'true',NULL,NULL,[]),
  (3209,3002,'DIFICULDADE_CICATRIZACAO','Já apresentou dificuldade de cicatrização?','BOOLEAN',TRUE,9,NULL,NULL,'CICATRIZACAO','DIFICULDADE DE CICATRIZAÇÃO',[]),
  (3210,3002,'SANGRAMENTO_EXAGERADO','Já apresentou sangramento excessivo ou alteração de coagulação?','BOOLEAN',TRUE,10,NULL,NULL,'SANGRAMENTO','RISCO DE SANGRAMENTO',[]),
  (3211,3002,'ANTICOAGULANTE','Usa anticoagulante ou antiagregante plaquetário?','BOOLEAN',TRUE,11,NULL,NULL,'ANTICOAGULANTE','USO DE ANTICOAGULANTE',[]),
  (3212,3002,'GESTANTE','Está gestante ou há possibilidade de gravidez?','BOOLEAN',TRUE,12,NULL,NULL,'GESTANTE','GESTAÇÃO INFORMADA',[]),
  (3213,3002,'DIABETES','Possui diabetes?','BOOLEAN',TRUE,13,NULL,NULL,'DIABETES','DIABETES',[]),
  (3214,3002,'HIPERTENSAO','Possui hipertensão arterial?','BOOLEAN',TRUE,14,NULL,NULL,'HIPERTENSAO','HIPERTENSÃO',[]),
  (3215,3002,'PROBLEMA_CARDIACO','Possui doença cardíaca, usa marca-passo ou teve endocardite?','BOOLEAN',TRUE,15,NULL,NULL,'CARDIACO','CONDIÇÃO CARDÍACA',[]),
  (3216,3002,'PROBLEMA_FIGADO','Possui doença no fígado?','BOOLEAN',TRUE,16,NULL,NULL,'FIGADO','CONDIÇÃO HEPÁTICA',[]),
  (3217,3002,'ASMATICO','Possui asma ou outra condição respiratória relevante?','BOOLEAN',TRUE,17,NULL,NULL,'ASMA','ASMA/CONDIÇÃO RESPIRATÓRIA',[]),
  (3218,3002,'FUMANTE','Fuma atualmente?','BOOLEAN',TRUE,18,NULL,NULL,'FUMANTE','TABAGISMO',[]),
  (3219,3002,'CIGARRO_ELETRONICO','Usa cigarro eletrônico ou vape?','BOOLEAN',TRUE,19,NULL,NULL,'VAPE','USO DE CIGARRO ELETRÔNICO',[]),
  (3220,3002,'TONTURAS','Costuma sentir tonturas ou desmaios?','BOOLEAN',TRUE,20,NULL,NULL,'TONTURA','TONTURAS OU DESMAIOS',[]),
  (3221,3002,'DOENCA_FAMILIA','Há doença relevante ou hereditária na família?','BOOLEAN',TRUE,21,NULL,NULL,NULL,NULL,[]),
  (3222,3002,'DOENCA_FAMILIA_DETALHE','Descreva a doença e o grau de parentesco.','TEXT',TRUE,22,3221,'true',NULL,NULL,[]),
  (3223,3002,'COMENTARIOS','Há outra informação de saúde importante para o atendimento odontológico?','TEXT',FALSE,23,NULL,NULL,NULL,NULL,[]),
  (3224,3002,'PROBLEMA_RENAL','Possui doença renal?','BOOLEAN',TRUE,24,NULL,NULL,'RENAL','CONDIÇÃO RENAL',[])
]) s ON t.id_pergunta=s.id_pergunta
WHEN NOT MATCHED THEN INSERT (id_pergunta,id_formulario,codigo,texto,tipo,obrigatoria,ordem,parent_question_id,show_when_value,alert_code,alert_template,options)
VALUES(s.id_pergunta,s.id_formulario,s.codigo,s.texto,s.tipo,s.obrigatoria,s.ordem,s.parent_question_id,s.show_when_value,s.alert_code,s.alert_template,s.options);

-- Retire the earlier demonstrative form from selection without changing its historical versions.
UPDATE `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_formularios`
SET status='RASCUNHO'
WHERE id_formulario=3001 AND status='PUBLICADO_TESTE';
