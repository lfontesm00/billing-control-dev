billing-control/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   │
│   │   ├── api/
│   │   │   ├── pacientes.py
│   │   │   ├── consultas.py
│   │   │   ├── procedimentos.py
│   │   │   └── pagamentos.py
│   │   │
│   │   ├── services/
│   │   │   ├── paciente_service.py
│   │   │   ├── consulta_service.py
│   │   │   ├── procedimento_service.py
│   │   │   └── pagamento_service.py
│   │   │
│   │   ├── repositories/
│   │   │   ├── paciente_repository.py
│   │   │   ├── consulta_repository.py
│   │   │   └── procedimento_repository.py
│   │   │
│   │   ├── models/
│   │   │   ├── paciente.py
│   │   │   ├── consulta.py
│   │   │   └── procedimento.py
│   │   │
│   │   ├── config/
│   │   │   └── settings.py
│   │   │
│   │   └── utils/
│   │       ├── cpf.py
│   │       └── datas.py
│   │
│   ├── tests/
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
│
├── frontend/
│   ├── web/
│   ├── desktop/
│   └── README.md
│
├── functions/
│   ├── importar-consultas/
│   │   ├── main.py
│   │   └── requirements.txt
│   │
│   └── processar-arquivo/
│       ├── main.py
│       └── requirements.txt
│
├── sql/
│   ├── raw/
│   ├── trusted/
│   ├── refined/
│   ├── procedures/
│   └── ddl/
│
├── docs/
│   ├── arquitetura.md
│   ├── modelo-dados.md
│   └── api.md
│
├── scripts/
│   ├── deploy-backend.sh
│   └── deploy-functions.sh
│
├── .github/
│   └── workflows/
│
├── .gitignore
├── cloudbuild.yaml
└── README.md