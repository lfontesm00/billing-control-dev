# Billing Control — Manual de primeiros passos, configuração e validação

Versão do manual: 21/08/2026.

Este documento descreve o estado real do MVP web, a preparação segura dos serviços externos, a integração com as tabelas históricas do BigQuery e o roteiro completo de validação. Ele deve ser atualizado sempre que uma rota, tabela, variável ou regra operacional mudar.

> **Proteção dos dados históricos:** não execute migrations no dataset real antes do preflight e da validação em uma cópia controlada. Nenhum SQL deste projeto foi executado no BigQuery real durante o desenvolvimento local.

## 1. O que existe atualmente

O MVP implementa o fluxo:

```text
Login → Organização → Clínica → Pacientes → Perfil → Anamnese → Histórico
```

Componentes disponíveis:

- frontend web React 19 + Vinext em `frontend/web`;
- API REST FastAPI em `backend/app`;
- Firebase Authentication por e-mail e senha;
- validação do ID token no backend;
- organizações, perfis, permissões e acesso por clínica;
- limite de três clínicas por organização;
- cadastro global de pacientes e vínculo com várias clínicas;
- responsável obrigatório para menores de 18 anos;
- pesquisa, perfil, inativação e reativação de pacientes;
- formulário configurável e clinicamente bloqueado por padrão;
- versões imutáveis de anamnese, aceite e alertas;
- modo paciente com token temporário e de uso único;
- idempotência e auditoria para operações críticas.

Fora do MVP atual:

- consultas, procedimentos, pagamentos e financeiro completo;
- odontograma funcional;
- operação offline;
- aplicativo desktop;
- ambiente publicado e CI/CD de produção.

### 1.1 Estado desta máquina

| Item | Estado verificado |
|---|---|
| Python | 3.14.2 |
| Node.js | 25.2.1 |
| npm | 11.6.2 |
| Google Cloud CLI (`gcloud`) | instalado em `C:\Users\User\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin`; a sessão atual do Codex ainda não recebeu esse caminho no `PATH` |
| `backend/.env` | criado localmente para o dataset de validação |
| `frontend/web/.env.local` | criado localmente com a configuração pública Firebase |
| ADC do Google Cloud | não validada |
| Firebase real | não validado |
| BigQuery real | não acessado |
| Testes backend | 13 aprovados |
| Lint e build frontend | aprovados |

Os testes atuais usam mocks e não alteram Firebase nem BigQuery.

### 1.2 Estrutura atual após a limpeza

```text
billing-control-dev/
├── backend/
│   ├── app/
│   │   ├── api/v1.py                 # todas as rotas funcionais
│   │   ├── core/                     # autenticação e erros
│   │   ├── models/mvp.py             # contratos Pydantic atuais
│   │   ├── repositories/mvp.py       # acesso Trusted e bc_*
│   │   ├── services/mvp.py           # regras de negócio
│   │   ├── utils/identifiers.py      # normalização, validação e IDs
│   │   └── main.py
│   ├── tests/
│   ├── .env.example
│   └── requirements.txt
├── frontend/web/                     # aplicação React/Vinext
├── functions/importar-consultas/     # automação de ingestão preservada
├── sql/
│   ├── ddl/
│   ├── trusted/
│   └── validation/
├── docs/
└── README.md
```

A API inicial sem versionamento foi removida. Não existem mais routers, models, services ou repositories paralelos para clínicas/pacientes, nem o sinalizador `ENABLE_LEGACY_ROUTES`. Também foram removidos `test-api.ps1`, `teste.sql` e a documentação backend que descrevia somente aqueles endpoints antigos.

Arquivos preservados intencionalmente:

- SQLs Trusted, migrations, seeds e reconciliações;
- documentação de engenharia de dados e frontend;
- Cloud Function de importação de consultas;
- frontend web e API `/api/v1`;
- testes automatizados atuais.

## 2. Arquitetura e fluxo dos dados

```text
Navegador
├── Firebase Authentication
│   └── ID token
└── FastAPI /api/v1
    ├── valida token, usuário e status
    ├── valida organização, clínica e permissão
    ├── aplica normalização e regras de negócio
    └── BigQuery: dataset_dev_trusted_clinica
        ├── tb_trat_billing_control_*: cadastros históricos e estado atual
        └── bc_*: recursos complementares exclusivos do sistema web
```

O navegador nunca acessa o BigQuery diretamente. Todas as consultas e escritas passam pela API.

A aplicação carrega atualmente 22 rotas FastAPI contando OpenAPI, Swagger, ReDoc e health. Todas as rotas de negócio estão em `backend/app/api/v1.py`.

### 2.1 Tabelas históricas obrigatórias

Estas tabelas permanecem como fonte única e não devem ser duplicadas:

| Tabela | Responsabilidade |
|---|---|
| `tb_trat_billing_control_clinicas` | cadastro operacional das clínicas |
| `tb_trat_billing_control_pacientes` | cadastro global dos pacientes |
| `tb_trat_billing_control_paciente_clinica` | vínculo e isolamento por clínica |
| `tb_trat_billing_control_anamnese_pacientes` | estado atual do perfil de saúde |

As demais tabelas históricas — doutores, doutor-clínica, consultas, procedimentos, consulta-procedimentos e despesas — continuam preservadas, mas seus módulos ainda não fazem parte deste MVP.

### 2.2 Tabelas complementares do sistema web

| Tabela | Responsabilidade |
|---|---|
| `bc_organizacoes` | proprietário lógico das clínicas |
| `bc_usuarios` | vínculo do usuário com Firebase e organização |
| `bc_organizacao_clinicas` | associação aos `id_clinica` históricos |
| `bc_perfis`, `bc_permissoes`, `bc_perfil_permissoes` | autorização reutilizável |
| `bc_usuario_perfis`, `bc_usuario_clinicas` | acesso do usuário |
| `bc_convites` | convites pendentes |
| `bc_responsaveis` | responsável legal do paciente |
| `bc_formularios`, `bc_perguntas` | definição versionada do formulário |
| `bc_anamnese_versoes` | respostas e aceites imutáveis |
| `bc_alertas_clinicos` | alertas derivados da versão vigente |
| `bc_sessoes_paciente` | tokens temporários do modo paciente |
| `bc_idempotencias` | proteção contra repetição de requisições |
| `bc_auditoria` | rastreabilidade das operações |

Não grave em `bc_clinicas`, `bc_pacientes` ou `bc_paciente_clinicas`. Caso tenham sido criadas em uma experiência anterior, mantenha-as isoladas e sem uso; não as remova automaticamente.

### 2.3 Regras de escrita

- IDs novos são `INT64` positivos derivados de UUID e verificados antes da inserção.
- Não existe mais `MAX(id) + 1` nos repositories.
- CPF/CNPJ e telefone são persistidos somente com dígitos.
- E-mail é convertido para minúsculas.
- Strings têm espaços externos removidos.
- Novos registros Trusted recebem `origem_registro='WEB_APP_V1'`.
- Inclusões recebem `created_at` e `updated_at`; alterações preservam `created_at`.
- Leituras históricas usam a linha de `updated_at`/`created_at` mais recente por ID.
- Paciente é global; o acesso clínico depende de `tb_trat_billing_control_paciente_clinica`.
- Cadastro de paciente, vínculo e conclusão de anamnese usam transações e idempotência.

### 2.4 Estado atual e histórico da anamnese

Ao concluir uma anamnese, uma única transação lógica:

1. cria uma versão imutável em `bc_anamnese_versoes`;
2. cria ou atualiza o estado atual em `tb_trat_billing_control_anamnese_pacientes`;
3. mantém `tb_trat_billing_control_pacientes.fk_anamnese_paciente` consistente;
4. substitui os alertas ativos;
5. registra idempotência e auditoria.

Todas as respostas ficam em `respostas_json`. A pergunta de alergia atualiza `flag_alergia_medicamento` e a de hipertensão atualiza `flag_hipertenso`. O mapeamento das demais perguntas para flags históricas específicas ainda deve ser ampliado quando o formulário clínico definitivo for aprovado.

## 3. Google Cloud

### 3.1 Validar a instalação, o PATH e o projeto

O Google Cloud CLI já está instalado para o usuário atual em:

```text
C:\Users\User\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd
```

Em um PowerShell novo, valide:

```powershell
gcloud --version
gcloud init
gcloud config set project datalake-dev-clinica-control
gcloud config get-value project
```

O último comando deve retornar `datalake-dev-clinica-control`.

Se `gcloud` funcionar no seu PowerShell normal, não é necessário reinstalar. Se uma sessão específica não reconhecer o comando, adicione temporariamente o diretório existente ao `PATH` dessa sessão:

```powershell
$gcloudBin = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin"
$env:Path = "$env:Path;$gcloudBin"
gcloud --version
```

Depois de alterar o `PATH` permanente do Windows, feche e abra novamente o terminal, a IDE e o Codex para que recebam o novo valor. O fato de o Codex não localizar o comando não significa que o SDK não esteja instalado.

### 3.2 Configurar credenciais locais

```powershell
gcloud auth application-default login
gcloud auth application-default set-quota-project datalake-dev-clinica-control
```

Valide sem registrar o token:

```powershell
gcloud auth application-default print-access-token | Measure-Object -Character
```

### 3.3 APIs e permissões

```powershell
gcloud services enable bigquery.googleapis.com identitytoolkit.googleapis.com firebase.googleapis.com
```

#### 3.3.1 Verificar se o projeto pertence a uma organização

Antes de configurar grupos, execute:

```powershell
gcloud projects describe datalake-dev-clinica-control `
  --format="table(projectId,parent.type,parent.id)"
```

Interpretação:

- `parent.type=organization`: o projeto pertence a uma organização;
- `parent.type=folder`: o projeto está em uma pasta que pertence a uma organização;
- campos de `parent` vazios: o projeto não está associado a uma organização.

A página **IAM e administrador → Grupos** não pode ser aberta tendo um projeto como recurso selecionado. Ela é uma página de administração centralizada e exige uma organização Google Cloud respaldada por Cloud Identity ou Google Workspace. Se houver organização, selecione-a no seletor de recursos antes de abrir **Grupos**.

Essa limitação da página não deve ser confundida com a política IAM do projeto. Um Google Group já existente pode ser informado diretamente como principal IAM, usando `group:endereco-do-grupo`, desde que o grupo exista e a conta atual tenha permissão para alterar a política. A criação e administração centralizada do grupo e dos seus membros, porém, depende da estrutura organizacional apropriada.

Se o projeto não possuir organização:

- não tente administrar o grupo pela página **Grupos** do Console;
- teste o grupo diretamente em **IAM do projeto** e em **Compartilhamento do dataset**;
- confirme o acesso efetivo com um membro do grupo;
- se o principal for recusado ou se for necessária governança centralizada, configure Cloud Identity/Google Workspace e associe o projeto a uma organização;
- como alternativa temporária de desenvolvimento, conceda acesso individual mínimo, documentando que deverá ser substituído pelo grupo;
- para a aplicação em produção, use uma service account exclusiva, e não uma conta humana.

#### 3.3.2 Permissões do grupo

O modelo preferido de acesso humano é conceder os papéis ao grupo, não individualmente:

```text
gcp-dev-billing-control-clinca@googlegroups.com
```

O membro IAM correspondente é `group:gcp-dev-billing-control-clinca@googlegroups.com`.

> **Atenção à grafia:** o grupo existente usa `clinca`, sem o segundo `i`. O endereço `gcp-dev-billing-control-clinica@googlegroups.com` foi rejeitado pelo Console como uma conta/principal inexistente. Não “corrija” o nome ao copiar.

Permissões mínimas para desenvolver e validar este MVP:

| Escopo | Papel | Motivo |
|---|---|---|
| projeto `datalake-dev-clinica-control` | `roles/bigquery.jobUser` | criar e executar jobs/queries |
| somente dataset `dataset_dev_trusted_clinica` | `roles/bigquery.dataEditor` | ler e alterar tabelas necessárias ao MVP |

Aplicar o papel no projeto:

```powershell
gcloud projects add-iam-policy-binding datalake-dev-clinica-control `
  --member="group:gcp-dev-billing-control-clinca@googlegroups.com" `
  --role="roles/bigquery.jobUser" `
  --condition=None
```

Para o dataset, use preferencialmente o Console do Google Cloud. O comando `bq add-iam-policy-binding` não oferece suporte a datasets, e alterações do bloco de acesso por API/JSON podem sobrescrever permissões existentes se a configuração completa não for preservada.

Procedimento recomendado:

1. abra o **Google Cloud Console**;
2. acesse **BigQuery**;
3. selecione o dataset `dataset_dev_trusted_clinica`;
4. abra **Sharing / Compartilhamento**;
5. abra **Permissions / Permissões**;
6. clique em **Add principal / Adicionar principal**;
7. informe `gcp-dev-billing-control-clinca@googlegroups.com`;
8. atribua **BigQuery Data Editor** (`roles/bigquery.dataEditor`);
9. salve;
10. reabra as permissões e confirme que o grupo aparece somente com o papel desejado naquele dataset.

Não use um comando que reaplique toda a política JSON enquanto estiver começando. Esse método só deve ser usado depois de exportar, preservar e revisar todos os acessos existentes.

Validar o vínculo do projeto:

```powershell
gcloud projects get-iam-policy datalake-dev-clinica-control `
  --flatten="bindings[].members" `
  --filter="bindings.members:group:gcp-dev-billing-control-clinca@googlegroups.com" `
  --format="table(bindings.role,bindings.members)"
```

Depois de aplicar os acessos, revise os demais papéis do grupo no projeto. Antes de remover qualquer papel existente, confirme se ele sustenta pipelines, Storage ou outras equipes; não faça remoções automáticas durante o setup do MVP.

Para produção, prefira uma service account exclusiva da API, também com papéis limitados. Não use chaves privadas no repositório e não conceda `Owner`, `Editor` ou `BigQuery Admin`.

## 4. BigQuery — preparação segura

Dataset atual:

```text
datalake-dev-clinica-control.dataset_dev_trusted_clinica
```

### 4.1 Ordem obrigatória

1. [x] Execute somente `sql/validation/004_trusted_preflight.sql` no dataset real.
2. [x] Confirme schemas, quantidades, duplicatas e vínculos órfãos.
3. [x] Execute `sql/validation/007_financial_baseline.sql` e exporte os três resultados como baseline.
4. [x] Crie uma cópia controlada do dataset para validação, na mesma região.
5. [x] Confirme que os scripts apontam para `dataset_dev_trusted_clinica_validacao`. Nesta etapa, todos os SQLs do diretório `sql/` já estão configurados e identificados para executar exclusivamente na cópia controlada.
6. [x] Na cópia, execute `sql/ddl/001_mvp_core.sql`.
7. [x] Na cópia, execute `sql/ddl/003_trusted_web_compatibility.sql`.
8. [x] Execute `sql/trusted/002_seed_mvp.sql`.
9. [x] Configure Firebase/API e crie o proprietário por `POST /api/v1/setup`.
10. [x] Descubra o `id_organizacao` e o `id_usuario` criados.
11. [x] Substitua os dois valores `0` em `sql/trusted/005_map_existing_clinics.sql` e execute o script para associar organização e administrador às clínicas históricas.
12. [ ] Faça todos os testes funcionais. **Em andamento.**
13. [ ] Execute `sql/validation/006_trusted_reconciliation.sql`.
14. [ ] Execute novamente `007_financial_baseline.sql` e compare quantidade, datas e valores por clínica/status com a baseline exportada.
15. [ ] Promova para o dataset principal somente depois de reconciliar a base histórica e o resumo financeiro.

> **Estado atual:** os passos 1 a 11 foram concluídos na cópia controlada. Organização `3965055167959469407`, usuário administrador `2842519271168443175` e clínica histórica `1` estão associados e ativos; o login exibe a clínica e seus pacientes históricos. O próximo passo é o 12, testes funcionais. Para uma promoção futura, não faça substituição manual silenciosa: revise os SQLs, gere uma versão de promoção e repita o preflight imediatamente antes da execução no dataset principal.

#### Passo 9 detalhado — Firebase, API e proprietário

- [x] adicionar o Firebase ao projeto GCP existente, sem criar outro projeto;
- [x] manter o Google Analytics desativado para a validação;
- [x] habilitar o provedor `E-mail/senha`;
- [x] registrar o aplicativo Web `Billing Control Web Validação`;
- [x] criar `frontend/web/.env.local` com a configuração pública do Firebase;
- [x] criar `backend/.env` apontando para `dataset_dev_trusted_clinica_validacao` e com `AUTH_DISABLED=False`;
- [x] clicar em `Continuar no console` para encerrar o assistente do Firebase;
- [x] iniciar a API e validar `GET /health`;
- [x] iniciar o frontend e abrir `http://localhost:3000`;
- [x] cadastrar/autenticar o primeiro usuário por e-mail e senha;
- [x] informar o nome da organização na configuração inicial;
- [x] confirmar que `POST /api/v1/setup` retornou HTTP `201` e avançou para o cadastro de clínica;
- [ ] guardar o `id_organizacao` e o `id_usuario` retornados.

O passo 10 começa somente depois que todos os itens acima estiverem concluídos.

#### Resultado registrado do preflight em 21/08/2026

| Verificação | Resultado |
|---|---|
| schema das quatro tabelas históricas | localizado e compatível com a migração aditiva |
| pacientes | 219 linhas e 219 IDs únicos |
| anamneses | 219 linhas e 219 IDs únicos |
| IDs duplicados de pacientes | nenhum resultado |
| vínculos paciente-clínica órfãos | nenhum resultado |

As duas mensagens “Não há dados para exibir” são resultados positivos: a terceira consulta procura IDs duplicados e a quarta procura vínculos órfãos. Como ambas retornaram vazio, essas verificações passaram.

Na primeira execução da verificação adicional, uma referência de anamnese não encontrou correspondência exclusivamente por `anamnese.fk_anamnese_paciente`. Como o histórico possui simultaneamente `id_anamnese` e `fk_anamnese_paciente`, o preflight passou a classificar cada paciente como:

- `FK_ANAMNESE_PACIENTE`: vínculo encontrado pela coluna replicada;
- `ID_ANAMNESE`: vínculo legado aponta diretamente para a chave primária;
- `ID_PACIENTE`: fallback encontrado diretamente por `anamnese.id_paciente`;
- `SEM_CORRESPONDENCIA`: exceção histórica sem nenhuma das três correspondências.

O repository e a reconciliação aceitam as três formas históricas para leitura. Novos registros gravam `id_paciente` e usam o mesmo valor em `id_anamnese` e `fk_anamnese_paciente`, eliminando ambiguidade futura. Uma linha classificada como `SEM_CORRESPONDENCIA` pode ser registrada como exceção e mantida sem alteração quando o histórico clínico não for requisito de aceite; ela não deve ser apagada nem corrigida automaticamente.

Exceção histórica registrada: `id_paciente=219`, `fk_anamnese_paciente=0`, sem correspondência pelas três chaves. O registro será preservado como está e não bloqueia o MVP, pois o histórico clínico anterior não faz parte do critério de aceite. Os novos preenchimentos desse paciente criarão referências consistentes.

#### Baseline financeira registrada em 21/08/2026

| Origem | Clínica | Status | Quantidade | Valor | Período/observação |
|---|---:|---|---:|---:|---|
| consultas | 1 | FINALIZADA | 201 | 46.555,50 | 07/01/2026 a 08/07/2026 |
| itens de consulta | 1 | — | 224 | 60.705,50 | 187 consultas distintas |
| despesas | 1 | NOK | 1 | 62,75 | 30/01/2026 |
| despesas | 1 | OK | 59 | 9.032,63 | 08/01/2026 a 25/07/2026 |

O valor dos itens não precisa ser igual ao total das consultas: eles medem campos e granularidades diferentes. O critério de preservação é cada linha permanecer idêntica à própria baseline depois da validação. O script `007` agora inclui comparações automáticas e deve retornar `OK` em todas as linhas; qualquer `DIVERGENTE` bloqueia a promoção até análise.

Colunas web que ainda não existem e serão adicionadas pelo script `003`:

- clínicas: `telefone`, `responsavel`, `cro_responsavel`, `origem_registro`;
- pacientes: `plano_odontologico`;
- paciente-clínica: `origem_registro`;
- anamnese: `id_formulario`, `respostas_json`, dados do aceite, versão dos termos, `aceito_em` e `origem_registro`.

As colunas já existentes usam `ADD COLUMN IF NOT EXISTS` e não serão recriadas.

### 4.2 O que cada SQL faz

| Script | Tipo | Efeito |
|---|---|---|
| `004_trusted_preflight.sql` | somente leitura | inventário e integridade anterior |
| `001_mvp_core.sql` | DDL aditivo | cria somente extensões `bc_*` necessárias |
| `003_trusted_web_compatibility.sql` | DDL aditivo | adiciona colunas web ausentes nas tabelas históricas |
| `002_seed_mvp.sql` | MERGE idempotente | perfis, permissões e formulário demonstrativo |
| `005_map_existing_clinics.sql` | MERGE idempotente | associa clínicas históricas à organização |
| `006_trusted_reconciliation.sql` | somente leitura | confere base mínima de 219 pacientes/anamneses e órfãos |
| `007_financial_baseline.sql` | somente leitura | registra e compara quantidades, datas e totais de consultas, itens e despesas com a baseline de 21/08/2026 |
| `008_remove_unsafe_test_clinic.sql` | limpeza controlada | remove somente a clínica fictícia criada com ID inseguro; já executado na validação |
| `009_publish_test_anamnesis.sql` | atualização controlada | publica o formulário 3001 como `PUBLICADO_TESTE`, sem aprovação clínica |
| `010_unpublish_test_anamnesis.sql` | reversão controlada | retorna o formulário técnico a `RASCUNHO` após os testes |

O script `003` não apaga, renomeia, trunca ou regrava linhas.

### 4.3 Conferências essenciais

Clínicas históricas associadas:

```sql
SELECT oc.id_organizacao,c.id_clinica,c.nome_clinica
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_organizacao_clinicas` oc
JOIN `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_clinicas` c USING(id_clinica)
WHERE oc.ativo
ORDER BY c.nome_clinica;
```

Perfis e permissões:

```sql
SELECT p.codigo perfil,ARRAY_AGG(pm.codigo ORDER BY pm.codigo) permissoes
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_perfis` p
JOIN `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_perfil_permissoes` pp USING(id_perfil)
JOIN `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_permissoes` pm USING(id_permissao)
GROUP BY p.codigo ORDER BY p.codigo;
```

Resultados esperados:

- `FULL_ACCESS`: todas as permissões;
- `RECEPCAO`: pacientes, anamnese e modo paciente;
- `FINANCEIRO`: somente permissões financeiras reservadas.

## 5. Firebase Authentication

### 5.1 Criar o app web

No Firebase Console do projeto:

1. abra Configurações do projeto;
2. registre um app Web;
3. copie `apiKey`, `authDomain` e `projectId`;
4. em Authentication → Sign-in method, habilite Email/Password;
5. inclua `localhost` nos domínios autorizados para desenvolvimento.

### 5.2 Antes de produção

- definir política de senha;
- habilitar proteção contra enumeração de e-mails;
- exigir `email_verified` também na API;
- configurar recuperação de senha;
- bloquear criação pública de novos proprietários após o primeiro bootstrap.

Os três últimos comportamentos ainda não estão completos no código atual.

## 6. Variáveis de ambiente

### 6.1 Backend

```powershell
Copy-Item backend\.env.example backend\.env
```

```dotenv
GCP_PROJECT=datalake-dev-clinica-control
BIGQUERY_DATASET_TRUSTED=dataset_dev_trusted_clinica_validacao
API_PREFIX=/api/v1
FIREBASE_PROJECT_ID=datalake-dev-clinica-control
AUTH_DISABLED=False
ALLOW_UNVALIDATED_TEST_FORMS=True
PATIENT_SESSION_MINUTES=30
CORS_ORIGINS=http://localhost:3000
```

Regras:

- `AUTH_DISABLED=False` em testes integrados e produção;
- `ALLOW_UNVALIDATED_TEST_FORMS=True` somente com o dataset `_validacao`; mantenha `False` em qualquer outro ambiente;
- durante os passos 9 a 14, `BIGQUERY_DATASET_TRUSTED` deve permanecer como `dataset_dev_trusted_clinica_validacao`;
- não use `BQ_DATASET`: esse nome não é lido pela configuração atual da API;
- origens CORS são separadas por vírgula e não levam barra final.

### 6.2 Frontend

```powershell
Copy-Item frontend\web\.env.example frontend\web\.env.local
```

```dotenv
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000/api/v1
NEXT_PUBLIC_FIREBASE_API_KEY=VALOR_DO_FIREBASE
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=datalake-dev-clinica-control.firebaseapp.com
NEXT_PUBLIC_FIREBASE_PROJECT_ID=datalake-dev-clinica-control
NEXT_PUBLIC_SITE_URL=http://localhost:3000
```

Configurações públicas do Firebase podem ficar no frontend. Service account, chave privada e tokens não podem.

```powershell
git check-ignore backend/.env frontend/web/.env.local
```

## 7. Instalação e execução local

Na raiz do projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Dependências backend mantidas:

- FastAPI e Uvicorn;
- Pydantic e pydantic-settings;
- cliente BigQuery;
- Firebase Admin;
- python-dotenv;
- pytest para desenvolvimento/testes.

As dependências sem uso `google-cloud-storage`, `httpx` e `pytest-asyncio` foram removidas de `backend/requirements.txt`.

Frontend:

```powershell
Set-Location frontend\web
npm install
Set-Location ..\..
```

Terminal do backend:

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal do frontend:

```powershell
Set-Location frontend\web
npm run dev
```

Endereços:

- frontend: `http://localhost:3000`;
- health: `http://127.0.0.1:8000/health`;
- Swagger: `http://127.0.0.1:8000/docs`.

Resposta esperada do health:

```json
{"status":"ok","app":"Billing Control API"}
```

## 8. Rotas disponíveis

| Área | Método e rota |
|---|---|
| Bootstrap | `POST /api/v1/setup` |
| Identidade | `GET /api/v1/me` |
| Clínicas do usuário | `GET /api/v1/me/clinicas` |
| Clínica | `POST /api/v1/clinicas` |
| Perfis | `GET /api/v1/perfis` |
| Convites | `POST /api/v1/convites` |
| Pacientes | `GET/POST /api/v1/clinicas/{clinic_id}/pacientes` |
| Vínculo | `POST /api/v1/clinicas/{clinic_id}/pacientes/{patient_id}/vinculo` |
| Perfil | `GET /api/v1/clinicas/{clinic_id}/pacientes/{patient_id}` |
| Histórico | `GET /api/v1/clinicas/{clinic_id}/pacientes/{patient_id}/anamnese/historico` |
| Status do paciente | `POST .../{patient_id}/inativar` e `POST .../{patient_id}/reativar` |
| Formulário | `GET /api/v1/clinicas/{clinic_id}/anamnese/formulario` |
| Modo paciente | `POST /api/v1/clinicas/{clinic_id}/modo-paciente` |
| Formulário público restrito | `GET /api/v1/modo-paciente/formulario` |
| Conclusão restrita | `POST /api/v1/modo-paciente/anamnese` |

Todas as rotas administrativas/clínicas exigem Bearer token Firebase. As duas últimas usam exclusivamente `X-Patient-Session`.

## 9. Primeiro acesso com histórico existente

1. Cadastre/autentique o proprietário no Firebase.
2. Chame `POST /api/v1/setup` com o nome da organização.
3. Consulte `bc_organizacoes` e copie o novo `id_organizacao`.
4. Configure e execute `005_map_existing_clinics.sql`.
5. Recarregue `GET /api/v1/me/clinicas`.
6. Confirme que os IDs e nomes são os mesmos das clínicas históricas.
7. Abra uma clínica e confirme a exibição dos pacientes já carregados.

Não recadastre uma clínica histórica apenas para fazê-la aparecer. O procedimento correto é criar o vínculo em `bc_organizacao_clinicas`.

## 10. Roteiro completo de testes funcionais

Use dataset de validação e dados fictícios. Não use novos dados reais de pacientes.

### 10.1 Infraestrutura

- [ ] `/health` responde 200;
- [ ] Swagger abre;
- [ ] frontend inicia sem erro de Firebase;
- [ ] não há erro CORS;
- [ ] API executa `SELECT 1` no BigQuery;
- [ ] token inválido ou expirado recebe 401.

### 10.2 Histórico preservado

- [ ] preflight identifica pelo menos 219 pacientes e 219 anamneses;
- [ ] IDs históricos não foram modificados;
- [ ] clínicas históricas aparecem após o mapeamento;
- [ ] pacientes aparecem somente nas clínicas vinculadas;
- [ ] perfil expõe `current_anamnesis` com o estado histórico;
- [ ] não existem novos órfãos.

### 10.3 Organização e clínicas

- [ ] proprietário recebe `FULL_ACCESS`;
- [ ] senha não aparece no BigQuery ou logs;
- [x] criação de clínica grava na tabela histórica e cria o vínculo organizacional;
- [ ] CPF/CNPJ duplicado é rejeitado;
- [x] segunda clínica funciona; terceira clínica ainda não testada;
- [ ] quarta clínica retorna `CLINIC_LIMIT_REACHED`;
- [x] troca entre a clínica histórica e a segunda clínica não mistura pacientes.

### 10.4 Paciente adulto

- [x] CPF, telefone e e-mail são normalizados;
- [x] cadastro cria paciente histórico e vínculo na mesma transação;
- [x] `origem_registro` é `WEB_APP_V1`;
- [x] pesquisa funciona por nome, CPF e telefone;
- [x] CPF aparece mascarado na listagem;
- [x] repetir a mesma `idempotency_key` não duplica registros.

Consulta de conferência:

```sql
WITH p AS (
  SELECT * FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_pacientes`
  QUALIFY ROW_NUMBER() OVER(PARTITION BY id_paciente ORDER BY updated_at DESC,created_at DESC)=1
), pc AS (
  SELECT * FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_paciente_clinica`
  QUALIFY ROW_NUMBER() OVER(PARTITION BY id_paciente,id_clinica ORDER BY updated_at DESC,created_at DESC)=1
)
SELECT p.id_paciente,p.nome_paciente,p.cpf_paciente,p.origem_registro,pc.id_clinica,pc.flag_paciente_ativo
FROM p JOIN pc USING(id_paciente)
ORDER BY p.updated_at DESC;
```

### 10.5 Menor de idade

- [x] menor sem responsável é rejeitado (teste automatizado);
- [x] CPF inválido do responsável é rejeitado (teste automatizado);
- [x] responsável válido é salvo em `bc_responsaveis`;
- [x] adulto não exige responsável.

### 10.6 Paciente global

- [x] mesmo CPF na mesma clínica retorna `PATIENT_ALREADY_LINKED`;
- [x] mesmo CPF sem vínculo retorna `PATIENT_EXISTS_NOT_LINKED` sem dados pessoais;
- [x] endpoint de vínculo reutiliza o `id_paciente` histórico;
- [x] nenhum segundo cadastro global é criado.

Limitação: a interface ainda não oferece a confirmação do vínculo nem recebe um identificador utilizável no conflito. Teste o endpoint diretamente com um ID previamente conhecido.

### 10.7 Inativação e reativação

- [x] inativação altera o estado atual do paciente e seus vínculos;
- [x] snapshots anteriores não são selecionados como estado vigente;
- [x] paciente inativo não aparece no filtro padrão;
- [x] reativação restaura o acesso;
- [x] ambas as ações geram auditoria.

Os botões ainda não existem no frontend; use Swagger.

### 10.8 Formulário e modo paciente

O seed nasce com `status='RASCUNHO'` e `validado_clinicamente=FALSE`. A validação técnica não deve declarar uma aprovação clínica inexistente.

- [x] modo paciente retorna `NO_VALIDATED_FORM` enquanto estiver bloqueado;
- [x] executar `009_publish_test_anamnesis.sql` e confirmar `PUBLICADO_TESTE`/`FALSE`;
- [x] interface mostra “Formulário de teste — sem validade clínica”;
- [x] configuração desativada continua bloqueando `PUBLICADO_TESTE` com `409 NO_VALIDATED_FORM`;
- [ ] dentista revisa perguntas, termos, condicionais e alertas;
- [ ] somente depois o formulário é publicado;
- [x] sessão expira no prazo configurado e cancelamento grava revogação;
- [ ] sessão não acessa outros pacientes ou rotas administrativas;
- [x] token funciona uma única vez.

Publicação técnica, somente no dataset de validação:

```sql
-- Execute o arquivo completo:
-- sql/validation/009_publish_test_anamnesis.sql
```

Após os testes, execute `sql/validation/010_unpublish_test_anamnesis.sql`. A publicação clínica real continua exigindo revisão de dentista, `status='PUBLICADO'` e `validado_clinicamente=TRUE`.

### 10.9 Conclusão da anamnese

O aceite do paciente e a aprovação clínica passam a ser etapas distintas. Antes de testar este fluxo, execute na cópia de validação:

1. `sql/ddl/011_professional_anamnesis_approval.sql`;
2. `sql/validation/012_seed_historical_anamnesis_v2.sql`.

O primeiro script adiciona somente colunas e a permissão `ANAMNESIS_APPROVE`. O segundo cria o formulário `3002`, versão 2, com 24 perguntas baseadas nos campos utilizados pela clínica histórica; ele não altera o formulário 3001, suas versões preenchidas nem as 219 anamneses legadas.

Depois do preenchimento, a versão nasce como `PENDENTE_APROVACAO`. Um usuário autenticado com `ANAMNESIS_APPROVE` deve revisar a versão e confirmar nome, CRO e responsabilidade profissional pelo endpoint `POST /api/v1/clinicas/{clinic_id}/pacientes/{patient_id}/anamnese/{version_id}/aprovar`. Somente então o prontuário fica `ATUALIZADA`.

Essa confirmação é uma assinatura eletrônica simples, vinculada à conta Firebase, ao nome, ao CRO e à data/hora UTC; não é uma assinatura manuscrita. O perfil `RECEPCAO` não recebe essa permissão. No seed inicial, apenas `FULL_ACCESS` pode aprovar.

- [x] perguntas obrigatórias são exigidas;
- [x] CPF do aceite é válido;
- [x] uma versão é criada em `bc_anamnese_versoes`;
- [x] estado atual é atualizado na tabela histórica;
- [x] `fk_anamnese_paciente` permanece consistente;
- [x] respostas anteriores não são alteradas;
- [x] alergia atualiza `flag_alergia_medicamento`;
- [x] hipertensão atualiza `flag_hipertenso`;
- [x] alertas verdadeiros aparecem no perfil;
- [x] repetição idempotente não cria outra versão (teste automatizado e contagem reconciliada);
- [x] validade termina no aniversário de um ano do aceite (teste unitário).
- [x] versão recém-preenchida aparece como `PENDENTE_APROVACAO`;
- [ ] usuário sem `ANAMNESIS_APPROVE` recebe `403`;
- [x] profissional registra nome, CRO e declaração de responsabilidade;
- [x] aprovação registra `ANAMNESIS_APPROVED` na auditoria;
- [x] somente a aprovação muda o status para `ATUALIZADA`;
- [x] repetir a aprovação retorna `409 ANAMNESIS_ALREADY_APPROVED` e não sobrescreve a assinatura profissional;

```sql
SELECT id_clinica,id_paciente,numero_versao,aceite_nome,termos_versao,aceito_em
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.bc_anamnese_versoes`
ORDER BY created_at DESC;

SELECT id_anamnese,fk_anamnese_paciente,id_paciente,id_clinica,flag_hipertenso,aceito_em,origem_registro,updated_at
FROM `datalake-dev-clinica-control.dataset_dev_trusted_clinica_validacao.tb_trat_billing_control_anamnese_pacientes`
ORDER BY updated_at DESC;
```

### 10.10 Permissões e auditoria

- [ ] `RECEPCAO` acessa pacientes, anamnese e modo paciente;
- [ ] `FINANCEIRO` não recebe acesso clínico implícito;
- [ ] usuário sem clínica recebe 403;
- [ ] usuário inativo recebe 403;
- [ ] IDs de outra organização não atravessam o isolamento;
- [ ] criação, vínculo, inativação, reativação e conclusão aparecem em `bc_auditoria`.

### 10.11 Gestão de equipe

Execute `sql/ddl/014_team_management.sql` somente no dataset `_validacao` e reinicie a API. A conta proprietária `FULL_ACCESS` passa a visualizar a opção `Equipe`.

O limite é de dois colaboradores ativos além do proprietário. Os perfis disponíveis são `RECEPCAO` e `FINANCEIRO`; `FULL_ACCESS` não pode ser delegado por esse fluxo.

1. Entre como proprietário e abra `Equipe`.
2. Cadastre nome, e-mail, perfil e pelo menos uma clínica.
3. Copie a senha temporária exibida uma única vez e entregue-a ao colaborador por canal seguro.
4. Entre como colaborador e confirme que o sistema exige uma nova senha antes de liberar as clínicas.
5. Como `RECEPCAO`, confirme acesso a pacientes e anamnese e bloqueio `403` ao tentar aprovar.
6. Valide edição de perfil/clínicas, redefinição de senha, inativação e reativação.

- [ ] proprietário mais dois colaboradores ativos são permitidos;
- [ ] terceiro colaborador ativo retorna `TEAM_MEMBER_LIMIT_REACHED`;
- [ ] senha temporária não aparece no BigQuery nem na auditoria;
- [ ] colaborador com troca pendente não acessa operações de negócio;
- [ ] usuário inativo recebe `USER_INACTIVE`, mesmo com token Firebase válido;
- [ ] `RECEPCAO` não possui `ANAMNESIS_APPROVE`;
- [ ] inativar libera uma vaga e reativar volta a respeitar o limite;
- [ ] auditorias `TEAM_MEMBER_CREATED`, `TEAM_MEMBER_UPDATED`, `TEAM_MEMBER_INACTIVATED`, `TEAM_MEMBER_REACTIVATED` e `TEAM_MEMBER_PASSWORD_RESET` foram registradas.

### 10.12 Pendências obrigatórias antes da promoção

Mesmo com a validação técnica concluída, a promoção para o dataset principal permanece bloqueada até concluir todos os itens abaixo:

1. [ ] Revisar e gerar SQLs específicos de promoção para o dataset principal.
2. [ ] Repetir o preflight no principal imediatamente antes da mudança.
3. [ ] Aplicar somente as migrações aditivas necessárias.
4. [ ] Mapear a organização e a clínica histórica no principal.
5. [ ] Definir o formulário clínico definitivo com revisão da dentista; os formulários atuais continuam sem validade clínica.
6. [ ] Preparar hospedagem HTTPS do frontend e da API, secrets e URLs públicas.
7. [ ] Repetir reconciliação e baseline após a promoção.

Nenhum SQL identificado como `VALIDATION TARGET` deve ser executado diretamente no dataset principal.

## 11. Testes automatizados

Backend:

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m pytest backend\tests -q
```

Resultado atual: `32 passed`. Há dois avisos de depreciação no ambiente local atual, sem falhas. Os testes cobrem regras de serviço, Trusted, deduplicação, transações, anamnese dual, normalização, colisão de ID e fundamentos da gestão de equipe. Eles não substituem testes reais do BigQuery/Firebase.

Frontend:

```powershell
Set-Location frontend\web
npm run lint
npm run build
```

Lint e build estão aprovados. Ainda não existem testes de componentes nem testes ponta a ponta.

## 12. Diagnóstico rápido

| Erro | Verificação |
|---|---|
| `gcloud` não reconhecido | adicionar `%LOCALAPPDATA%\Google\Cloud SDK\google-cloud-sdk\bin` ao `PATH` e reabrir a sessão; o SDK já está instalado |
| `DefaultCredentialsError` | executar `gcloud auth application-default login` |
| principal do grupo rejeitado como conta inativa/inexistente | conferir a grafia; o grupo atual é `gcp-dev-billing-control-clinca@googlegroups.com`, sem o segundo `i` |
| erro CORS | conferir `CORS_ORIGINS=http://localhost:3000` e reiniciar API |
| Firebase não configurado | preencher `.env.local` e reiniciar frontend |
| `SETUP_REQUIRED` | criar organização ou conferir convite/usuário interno |
| `FORBIDDEN` | conferir perfil, permissão, organização e clínica |
| clínica histórica não aparece | executar/conferir `005_map_existing_clinics.sql` |
| `NO_VALIDATED_FORM` | formulário ainda não foi aprovado e publicado |
| `PATIENT_EXISTS_NOT_LINKED` | confirmar vínculo explícito, sem recadastrar paciente |
| `PATIENT_NOT_IN_CLINIC` | conferir vínculo histórico ativo |
| repetição não idempotente | conferir chave e `bc_idempotencias` |

## 13. Pendências antes de produção

### Bloqueadores

- disponibilizar o `gcloud` no `PATH` das sessões que executarão o projeto e configurar ADC, Firebase e arquivos de ambiente;
- executar preflight e validar migrations em cópia controlada;
- reconciliar formalmente os 219 pacientes/anamneses;
- revisar e aprovar formulário e termos com profissional clínico/jurídico;
- exigir `email_verified` no backend;
- bloquear novos proprietários depois do bootstrap;
- implementar recuperação de senha;
- criar testes de integração BigQuery/Firebase e testes E2E;
- definir acesso, retenção, backup, descarte e resposta a incidentes conforme LGPD.

### Funcionalidades incompletas

- confirmação visual do vínculo de paciente existente;
- edição de paciente e responsável;
- botões web de inativação/reativação;
- atualização/inativação de clínica;
- envio automático de convites por e-mail;
- revogação/cancelamento explícito da sessão do paciente;
- mapeamento de todas as respostas para flags históricas específicas;
- testes de interface, monitoramento, logs estruturados, deploy e CI/CD.

### Riscos conhecidos

- BigQuery não garante constraints relacionais; a API e as reconciliações são responsáveis pela integridade;
- concorrência elevada pode exigir migração futura para banco transacional;
- scripts usam nomes explícitos de projeto/dataset e precisam ser revisados antes de cada ambiente;
- empates exatos de `updated_at`/`created_at` em snapshots legados devem ser identificados no preflight;
- dados clínicos não podem aparecer em logs, erros, telemetria ou ambientes não autorizados.

### Regra para novas limpezas

Antes de excluir outro arquivo, confirme que ele não é importado, não está listado nos scripts operacionais e não contém engenharia de dados ou documentação ainda necessária. Arquivos históricos do BigQuery e a Cloud Function não devem ser removidos apenas por não participarem das telas atuais.

## 14. Critério de aceite do MVP

O MVP só pode ser considerado validado quando:

- [ ] ambiente é reproduzível a partir deste manual;
- [ ] Firebase → API → BigQuery funciona ponta a ponta;
- [ ] 219 pacientes/anamneses históricos foram reconciliados sem perda;
- [ ] baseline financeira de consultas, itens e despesas permaneceu idêntica antes/depois;
- [ ] IDs históricos permanecem inalterados;
- [ ] isolamento foi testado com duas organizações e clínicas diferentes;
- [ ] três perfis de acesso foram testados;
- [ ] paciente adulto, menor e global foram validados;
- [ ] vínculo, inativação e reativação foram validados;
- [ ] anamnese bloqueada, publicada, atualizada e vencida foi validada;
- [ ] estado atual, versões, aceite, alertas e auditoria foram reconciliados;
- [ ] token expirado e token reutilizado são rejeitados;
- [ ] integração, interface e E2E passam;
- [ ] não existem credenciais ou dados pessoais em Git/logs;
- [ ] formulário, termos, segurança e LGPD têm aprovação responsável.

## Anamnese por link remoto — validação

Este fluxo é complementar ao modo paciente local. O link remoto não substitui a aprovação profissional e não constitui, isoladamente, prova absoluta de autoria.

1. Execute `sql/ddl/013_remote_anamnesis_links.sql` somente no dataset `_validacao`.
2. Gere um segredo fora do repositório com `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
3. No `backend/.env`, configure `EVIDENCE_HMAC_SECRET`, `EVIDENCE_HMAC_KEY_VERSION=v1`, `REMOTE_PATIENT_SESSION_HOURS=24` e `PUBLIC_SITE_URL`.
4. Para teste externo, `PUBLIC_SITE_URL` e a API precisam usar endereços HTTPS públicos; `localhost` só funciona no mesmo computador.
5. Reinicie backend e frontend, abra o perfil do paciente e clique em `Gerar link de anamnese`.
6. Abra o link em janela anônima e confirme CPF e nascimento. Para menor, use o CPF do responsável e o nascimento do paciente.
7. Confirme que cinco tentativas incorretas bloqueiam a sessão, que um novo link revoga o anterior e que o token desaparece da barra após a página abrir.
8. Envie a anamnese e valide `PENDENTE_APROVACAO`, uso único, evidências HMAC e auditorias.
9. Aprove com uma conta que possua `ANAMNESIS_APPROVE` e somente então confirme `ATUALIZADA` e alertas clínicos.

Nunca salve `EVIDENCE_HMAC_SECRET`, tokens completos ou dados pessoais em Git, logs, prints ou tickets.

### Pontos obrigatórios antes do uso dos links pelos pacientes

O endereço `http://localhost:3000` serve apenas para testes no computador da clínica. Ele não funciona no celular do paciente, porque `localhost` sempre representa o próprio aparelho que abriu o endereço.

Antes de disponibilizar os links para uso real:

- [ ] publicar o frontend em um endereço HTTPS, como Firebase Hosting;
- [ ] publicar a API FastAPI em um endereço HTTPS, como Cloud Run;
- [ ] configurar `PUBLIC_SITE_URL` com o domínio público do frontend;
- [ ] configurar `NEXT_PUBLIC_SITE_URL` com o mesmo domínio público;
- [ ] configurar `NEXT_PUBLIC_API_URL` com a URL HTTPS pública da API e o sufixo `/api/v1`;
- [ ] limitar `CORS_ORIGINS` ao domínio público do frontend;
- [ ] manter `EVIDENCE_HMAC_SECRET` somente no Secret Manager ou nas variáveis protegidas do serviço;
- [ ] configurar redirecionamento/rewrite para que `/anamnese/responder` abra diretamente, inclusive ao atualizar a página;
- [ ] testar o link em celular usando Wi-Fi e rede móvel, fora da rede da clínica;
- [ ] confirmar que o token desaparece da barra do navegador após a abertura;
- [ ] confirmar que HTTPS é válido e que nenhuma chamada usa conteúdo misto HTTP/HTTPS;
- [ ] validar expiração, revogação, bloqueio após cinco erros e uso único no ambiente publicado;
- [ ] revisar política de privacidade, termos, retenção das evidências e fluxo para menores com responsável jurídico/LGPD;
- [ ] configurar monitoramento e orçamento no GCP antes de habilitar tráfego real.

Exemplo de produção:

```env
# backend
PUBLIC_SITE_URL=https://datalake-dev-clinica-control.web.app
CORS_ORIGINS=https://datalake-dev-clinica-control.web.app
```

```env
# frontend
NEXT_PUBLIC_SITE_URL=https://datalake-dev-clinica-control.web.app
NEXT_PUBLIC_API_URL=https://SUA-API.run.app/api/v1
```

Alterar essas variáveis exige reiniciar/republicar o backend e recompilar/republicar o frontend. Não promover o dataset nem liberar links reais enquanto os itens acima estiverem pendentes.
