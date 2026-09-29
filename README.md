# Billing Control

MVP web para gestão de clínicas e pacientes odontológicos, com FastAPI, React/Vinext, Firebase Authentication e BigQuery.

## Arquitetura atual

```text
frontend/web → FastAPI /api/v1 → service → repository → BigQuery
```

- As tabelas históricas `tb_trat_billing_control_*` são a fonte de clínicas, pacientes, vínculos e estado atual da anamnese.
- As tabelas `bc_*` armazenam somente organização, usuários, permissões e extensões do sistema web.
- A API legada foi removida; todas as rotas funcionais estão sob `/api/v1`.

## Início rápido

Backend:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend, em outro terminal:

```powershell
Set-Location frontend\web
npm install
Copy-Item .env.example .env.local
npm run dev
```

- Frontend: `http://localhost:3000`
- Health: `http://127.0.0.1:8000/health`
- Swagger: `http://127.0.0.1:8000/docs`

## Testes

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m pytest backend\tests -q

Set-Location frontend\web
npm run lint
npm run build
```

## BigQuery

Não execute migrations diretamente no dataset histórico sem validação. A ordem segura é:

1. `sql/validation/004_trusted_preflight.sql`
2. validação em cópia controlada do dataset
3. `sql/ddl/001_mvp_core.sql`
4. `sql/ddl/003_trusted_web_compatibility.sql`
5. `sql/trusted/002_seed_mvp.sql`
6. `sql/trusted/005_map_existing_clinics.sql`
7. `sql/validation/006_trusted_reconciliation.sql`

## Documentação

Consulte [docs/manual-primeiros-passos.md](docs/manual-primeiros-passos.md) para configuração completa, Firebase, BigQuery, testes funcionais, diagnóstico e critérios de aceite.

Para continuar o SaaS com as áreas de Consultas, Doutores e Financeiro, leia também o [mapeamento detalhado das tabelas e relacionamentos](docs/mapeamento-dados-saas.md).
