-- VALIDATION TARGET: dataset_dev_trusted_clinica_validacao. Do not run against the primary dataset.
-- Billing Control MVP. Replace the project/dataset variables before execution.
DECLARE project_id STRING DEFAULT 'datalake-dev-clinica-control';
DECLARE dataset_id STRING DEFAULT 'dataset_dev_trusted_clinica_validacao';

CREATE TABLE IF NOT EXISTS `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_organizacoes` (
  id_organizacao INT64 NOT NULL, nome STRING NOT NULL, ativo BOOL NOT NULL,
  created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_usuarios` (
  id_usuario INT64 NOT NULL, id_organizacao INT64 NOT NULL, firebase_uid STRING,
  nome STRING NOT NULL, cpf STRING, email STRING NOT NULL, telefone STRING,
  ativo BOOL NOT NULL, created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL,
  troca_senha_obrigatoria BOOL, alterado_administrativamente_em TIMESTAMP,
  alterado_por_id_usuario INT64
);
CREATE TABLE IF NOT EXISTS `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_organizacao_clinicas` (
  id_organizacao_clinica INT64 NOT NULL, id_organizacao INT64 NOT NULL, id_clinica INT64 NOT NULL,
  ativo BOOL NOT NULL, created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_perfis` (
  id_perfil INT64 NOT NULL, codigo STRING NOT NULL, nome STRING NOT NULL, ativo BOOL NOT NULL
);
CREATE TABLE IF NOT EXISTS `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_permissoes` (
  id_permissao INT64 NOT NULL, codigo STRING NOT NULL, descricao STRING NOT NULL
);
CREATE TABLE IF NOT EXISTS `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_perfil_permissoes` (
  id_perfil_permissao INT64 NOT NULL, id_perfil INT64 NOT NULL, id_permissao INT64 NOT NULL
);
CREATE TABLE IF NOT EXISTS `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_usuario_perfis` (
  id_usuario_perfil INT64 NOT NULL, id_usuario INT64 NOT NULL, id_perfil INT64 NOT NULL, created_at TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_usuario_clinicas` (
  id_usuario_clinica INT64 NOT NULL, id_usuario INT64 NOT NULL, id_clinica INT64 NOT NULL,
  ativo BOOL NOT NULL, created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_convites` (
  id_convite INT64 NOT NULL, id_organizacao INT64 NOT NULL, email STRING NOT NULL,
  id_perfil INT64 NOT NULL, clinic_ids ARRAY<INT64>, status STRING NOT NULL,
  expires_at TIMESTAMP NOT NULL, created_by INT64 NOT NULL, created_at TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_responsaveis` (
  id_responsavel INT64 NOT NULL, id_paciente INT64 NOT NULL, nome STRING NOT NULL,
  cpf STRING NOT NULL, telefone STRING NOT NULL, email STRING, parentesco STRING NOT NULL,
  ativo BOOL NOT NULL, created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_formularios` (
  id_formulario INT64 NOT NULL, id_clinica INT64, nome STRING NOT NULL, versao INT64 NOT NULL,
  status STRING NOT NULL, validado_clinicamente BOOL NOT NULL, termos_versao STRING NOT NULL,
  termos_texto STRING NOT NULL, created_at TIMESTAMP NOT NULL, published_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_perguntas` (
  id_pergunta INT64 NOT NULL, id_formulario INT64 NOT NULL, codigo STRING NOT NULL,
  texto STRING NOT NULL, tipo STRING NOT NULL, obrigatoria BOOL NOT NULL, ordem INT64 NOT NULL,
  parent_question_id INT64, show_when_value STRING, alert_code STRING, alert_template STRING,
  options ARRAY<STRING>
);
CREATE TABLE IF NOT EXISTS `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_anamnese_versoes` (
  id_anamnese_versao INT64 NOT NULL, id_formulario INT64 NOT NULL, id_clinica INT64 NOT NULL,
  id_paciente INT64 NOT NULL, numero_versao INT64 NOT NULL, id_usuario_responsavel INT64,
  aceite_nome STRING NOT NULL, aceite_cpf STRING NOT NULL, termos_aceitos BOOL NOT NULL,
  termos_versao STRING NOT NULL, respostas_json JSON NOT NULL, aceito_em TIMESTAMP NOT NULL,
  created_at TIMESTAMP NOT NULL, status_aprovacao STRING, id_profissional_aprovador INT64,
  nome_profissional STRING, cro_profissional STRING, aprovado_em TIMESTAMP
  ,id_sessao_origem INT64,id_evidencia INT64,content_hmac STRING,key_version STRING,papel_confirmante STRING
) PARTITION BY DATE(created_at) CLUSTER BY id_clinica, id_paciente;
CREATE TABLE IF NOT EXISTS `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_alertas_clinicos` (
  id_alerta INT64 NOT NULL, id_anamnese_versao INT64 NOT NULL, id_clinica INT64 NOT NULL,
  id_paciente INT64 NOT NULL, codigo STRING NOT NULL, descricao STRING NOT NULL,
  ativo BOOL NOT NULL, created_at TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_sessoes_paciente` (
  id_sessao INT64 NOT NULL, token_hash STRING NOT NULL, id_clinica INT64 NOT NULL,
  id_paciente INT64 NOT NULL, id_usuario_criador INT64 NOT NULL, expires_at TIMESTAMP NOT NULL,
  revogada_em TIMESTAMP, usada BOOL NOT NULL, created_at TIMESTAMP NOT NULL
  ,tipo_sessao STRING,id_formulario INT64,versao_formulario INT64,verified_at TIMESTAMP,
  papel_confirmante STRING,tentativas_verificacao INT64,bloqueada_em TIMESTAMP,
  canal_compartilhamento STRING,key_version STRING
);
CREATE TABLE IF NOT EXISTS `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_anamnesis_evidence` (
  id_evidencia INT64 NOT NULL,id_sessao INT64 NOT NULL,id_clinica INT64 NOT NULL,id_paciente INT64 NOT NULL,
  id_formulario INT64,event_type STRING NOT NULL,request_id STRING NOT NULL,ip_hmac STRING NOT NULL,
  user_agent STRING,user_agent_hash STRING NOT NULL,content_hmac STRING,key_version STRING NOT NULL,
  origem_registro STRING NOT NULL,created_at TIMESTAMP NOT NULL
) PARTITION BY DATE(created_at) CLUSTER BY id_clinica,id_paciente,id_sessao;
CREATE TABLE IF NOT EXISTS `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_idempotencias` (
  id_idempotencia INT64 NOT NULL, chave STRING NOT NULL, operacao STRING NOT NULL,
  result_json STRING NOT NULL, created_at TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_auditoria` (
  id_auditoria INT64 NOT NULL, id_usuario INT64, id_organizacao INT64, id_clinica INT64,
  acao STRING NOT NULL, entidade STRING NOT NULL, id_entidade INT64 NOT NULL, created_at TIMESTAMP NOT NULL
) PARTITION BY DATE(created_at) CLUSTER BY id_organizacao, id_clinica;

-- BigQuery constraints are documentary and are not enforced. Services/repositories enforce them.
