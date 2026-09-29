# MVP Web — execução e configuração

## Componentes

- `backend/`: FastAPI, Firebase Admin e repositories BigQuery.
- `frontend/web/`: aplicação web responsiva em React/Vinext.
- `sql/ddl/001_mvp_core.sql`: tabelas operacionais do MVP.
- `sql/trusted/002_seed_mvp.sql`: perfis, permissões e formulário demonstrativo.

O formulário demonstrativo nasce como `RASCUNHO` e `validado_clinicamente = FALSE`. No dataset de validação, ele pode usar `PUBLICADO_TESTE` quando `ALLOW_UNVALIDATED_TEST_FORMS=True`, sempre identificado como sem validade clínica. Produção aceita apenas `PUBLICADO` com aprovação clínica explícita.

## Preparar o BigQuery

1. Revise o projeto e dataset nos dois scripts SQL.
2. Execute primeiro `001_mvp_core.sql` e depois `002_seed_mvp.sql`.
3. Não execute os scripts em produção sem revisão do formulário clínico.

## Firebase

Ative o provedor Email/Senha no Firebase Authentication do projeto. O backend usa Application Default Credentials; nenhuma senha ou chave de service account deve ser versionada.

No backend, copie `.env.example` para `.env` e preencha `FIREBASE_PROJECT_ID` e `CORS_ORIGINS`. Em desenvolvimento, use `CORS_ORIGINS=http://localhost:3000`. Ative `ALLOW_UNVALIDATED_TEST_FORMS=True` exclusivamente quando a API apontar para o dataset `_validacao`.

No frontend, copie `.env.example` para `.env.local` e preencha as configurações públicas do app web Firebase e `NEXT_PUBLIC_API_URL`.

## Executar

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Em outro terminal:

```powershell
Set-Location frontend\web
npm run dev
```

Acesse `http://localhost:3000`. O fluxo inicial cria a organização, cadastra a primeira clínica e abre a área de pacientes.

## Testar

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m pytest backend\tests -q
Set-Location frontend\web
npm run build
```

Testes que executam queries reais devem usar outro dataset e credenciais GCP explícitas. Os testes unitários não dependem de Firebase nem BigQuery.

## Publicação

Antes de publicar, configure:

- URL HTTPS pública do backend em `NEXT_PUBLIC_API_URL`;
- configurações públicas do Firebase no frontend;
- origem final do site em `CORS_ORIGINS` no backend;
- service account do Cloud Run com acesso mínimo ao dataset;
- formulário clinicamente revisado e publicado.

O frontend não persiste dados clínicos em `localStorage` ou IndexedDB. A sessão de autenticação Firebase permanece apenas durante a sessão do navegador.
