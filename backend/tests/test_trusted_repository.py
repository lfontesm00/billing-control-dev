from datetime import date

from app.models.mvp import ClinicCreate, PatientCreate
from app.repositories.mvp import BigQueryMvpRepository


class EmptyClient:
    pass


def repository():
    repo = BigQueryMvpRepository(client=EmptyClient())
    repo._unique_id = lambda *_: 9001
    return repo


def test_patient_read_uses_trusted_tables_and_latest_rows():
    repo = repository()
    captured = {}

    def query(sql, params=None):
        captured["sql"] = sql
        return []

    repo._query = query
    result = repo.list_patients(10, "Maria", True, 1, 25)
    assert result["items"] == []
    assert "tb_trat_billing_control_pacientes" in captured["sql"]
    assert "tb_trat_billing_control_paciente_clinica" in captured["sql"]
    assert "ROW_NUMBER() OVER(PARTITION BY id_paciente" in captured["sql"]
    assert "@digits!=''" in captured["sql"]
    assert "bc_pacientes" not in captured["sql"]


def test_patient_list_keeps_total_when_requested_page_is_empty():
    repo = repository()
    repo._query = lambda *_args, **_kwargs: [{"total": 51, "items": []}]
    result = repo.list_patients(10, "", True, 4, 25, "PENDENTE")
    assert result == {"items": [], "total": 51, "page": 4, "page_size": 25}


def test_clinic_panel_uses_all_active_patients_and_limits_priorities():
    repo = repository()
    captured = {}
    repo._query = lambda sql, params=None: captured.setdefault("sql", sql) and [{"pacientes_ativos": 30, "pendentes_preenchimento": 20, "pendentes_aprovacao": 3, "atualizadas": 6, "vencidas": 1, "prioridades": []}]
    result = repo.clinic_panel(10)
    assert result["pacientes_ativos"] == 30
    assert "COUNTIF(anamnese_status='PENDENTE_APROVACAO')" in captured["sql"]
    assert "LIMIT 5" in captured["sql"]


def test_identity_uses_joined_aggregates_supported_by_bigquery():
    repo = repository()
    captured = {}
    repo._query = lambda sql, params=None: captured.setdefault("sql",sql) and []
    from app.core import CurrentUser
    repo.resolve_identity(CurrentUser("firebase-uid","owner@example.com"))
    sql = captured["sql"]
    assert "profile_codes AS" in sql and "permission_codes AS" in sql
    assert "ARRAY(SELECT" not in sql


def test_patient_write_is_atomic_and_preserves_lineage():
    repo = repository()
    statements = []

    def query(sql, params=None):
        statements.append(sql)
        return []

    repo._query = query
    repo.create_patient_with_link(10, {
        "nome": "Maria Silva", "cpf": "52998224725", "data_nascimento": date(1990, 1, 1),
        "sexo": "FEMININO", "telefone": None, "email": None, "endereco": None,
        "plano_odontologico": None, "responsavel": None, "idempotency_key": "request-123",
    }, 20)
    sql = statements[-1]
    assert "BEGIN TRANSACTION" in sql and "COMMIT TRANSACTION" in sql
    assert "tb_trat_billing_control_pacientes" in sql
    assert "tb_trat_billing_control_paciente_clinica" in sql
    assert "origem_registro" in sql and "@source" in sql
    assert "bc_idempotencias" in sql and "bc_auditoria" in sql
    assert "IF @guardian IS NOT NULL THEN" in sql
    assert "WHERE @guardian IS NOT NULL" not in sql
    assert "MAX(id_paciente)" not in sql


def test_anamnesis_dual_write_is_one_transaction():
    repo = repository()
    statements = []
    captured_params = []
    results = iter([
        [],  # idempotency cache
        [{"fk_anamnese_paciente": 77}],
        [{"id_formulario": 30, "questions": []}],
        [],  # questions
        [],  # transaction
        [{"result_json": '{"id_anamnese_versao":9001,"numero_versao":1,"status":"ATUALIZADA"}'}],
    ])

    def query(sql, params=None):
        statements.append(sql)
        captured_params.append(params or [])
        return next(results)

    repo._query = query
    repo.submit_anamnesis(10, 40, {
        "form_id": 30, "form_version": 1, "terms_version": "terms-v1", "answers": [],
        "acceptance": {"nome": "Maria", "cpf": "52998224725"},
        "idempotency_key": "submit-123",
    }, 20)
    transaction = next(sql for sql in statements if "MERGE" in sql)
    assert "bc_anamnese_versoes" in transaction
    assert "tb_trat_billing_control_anamnese_pacientes" in transaction
    assert "flag_alergia_medicamento" in transaction
    assert "flag_hipertenso" in transaction
    assert "UPDATE `" in transaction and "tb_trat_billing_control_pacientes" in transaction
    assert "bc_alertas_clinicos" in transaction
    assert "CAST(JSON_VALUE(item,'$.id') AS INT64)" in transaction
    assert "INT64(JSON_VALUE(item,'$.id'))" not in transaction
    assert "bc_idempotencias" in transaction and "bc_auditoria" in transaction
    assert transaction.index("DECLARE next_version") < transaction.index("BEGIN TRANSACTION")
    transaction_index = statements.index(transaction)
    params_by_name = {param.name: param for param in captured_params[transaction_index]}
    assert params_by_name["terms"].value == "terms-v1"
    assert params_by_name["answers"].value == []
    assert params_by_name["alerts"].value == []


def test_repeated_anamnesis_key_returns_cached_result_without_new_transaction():
    repo = repository()
    statements = []

    def query(sql, params=None):
        statements.append(sql)
        return [{"result_json": '{"id_anamnese_versao":9001,"numero_versao":1,"status":"ATUALIZADA"}'}]

    repo._query = query
    result = repo.submit_anamnesis(10, 40, {
        "form_id": 30, "form_version": 1, "terms_version": "terms-v1", "answers": [],
        "acceptance": {"nome": "Maria", "cpf": "52998224725"},
        "idempotency_key": "submit-repeated",
    }, 20)
    assert result == {"id_anamnese_versao":9001,"numero_versao":1,"status":"ATUALIZADA"}
    assert len(statements) == 1
    assert "SUBMIT_ANAMNESIS" in statements[0]
    assert not any("BEGIN TRANSACTION" in sql for sql in statements)


def test_input_models_normalize_trusted_values():
    clinic = ClinicCreate(nome="  Clínica A  ", razao_social="  Clínica A Ltda  ", cnpj_cpf="11.222.333/0001-81", email=" A@EXAMPLE.COM ", telefone="(11) 99999-0000")
    patient = PatientCreate(nome="  Maria  ", cpf="529.982.247-25", data_nascimento=date(1990, 1, 1), telefone="(11) 98888-7777", email=" M@EXAMPLE.COM ", idempotency_key="request-123")
    assert clinic.nome == "Clínica A" and clinic.cnpj_cpf == "11222333000181"
    assert clinic.email == "a@example.com" and clinic.telefone == "11999990000"
    assert patient.nome == "Maria" and patient.cpf == "52998224725"
    assert patient.email == "m@example.com" and patient.telefone == "11988887777"


def test_uuid_int64_collision_is_retried(monkeypatch):
    repo = BigQueryMvpRepository(client=EmptyClient())
    candidates = iter([101, 202])
    monkeypatch.setattr("app.repositories.mvp.new_int64_id", lambda: next(candidates))
    totals = iter([[{"total": 1}], [{"total": 0}]])
    repo._query = lambda *_args, **_kwargs: next(totals)
    assert repo._unique_id("`dataset.table`", "id") == 202


def test_generated_int64_is_positive_and_javascript_safe():
    from app.utils.identifiers import new_int64_id

    generated = [new_int64_id() for _ in range(100)]
    assert all(0 < value <= (1 << 53) - 1 for value in generated)
    assert len(set(generated)) == len(generated)


def test_team_member_creation_enforces_limit_and_never_persists_password():
    repo = repository()
    statements = []
    captured_params = []
    def query(sql, params=None):
        statements.append(sql); captured_params.extend(params or []); return []
    repo._query = query
    repo.create_team_member(10,"firebase-uid",{"nome":"Recepção","email":"recepcao@example.com","profile_code":"RECEPCAO","clinic_ids":[1]},20)
    sql = statements[-1]
    assert "TEAM_MEMBER_LIMIT_REACHED" in sql
    assert "troca_senha_obrigatoria" in sql
    assert not any(param.name in {"password","senha","senha_temporaria"} for param in captured_params)
    assert "TEAM_MEMBER_CREATED" in sql


def test_team_member_reactivation_rechecks_limit():
    repo = repository()
    statements = []
    repo._query = lambda sql, params=None: statements.append(sql) or []
    repo.set_team_member_active(10,30,True,20)
    assert "TEAM_MEMBER_LIMIT_REACHED" in statements[-1]
    assert "TEAM_MEMBER_REACTIVATED" in [param.value for param in repo._params(action=("STRING","TEAM_MEMBER_REACTIVATED"))]


def test_form_query_gates_technical_status_with_setting():
    repo = repository()
    statements = []
    repo._query = lambda sql, params=None: statements.append(sql) or []
    assert repo.get_form(10) is None
    assert "status='PUBLICADO_TESTE'" in statements[0]
    assert "@allow_test" in statements[0]


def test_patient_session_resolution_requires_unused_unrevoked_unexpired_token():
    repo = repository()
    statements = []
    repo._query = lambda sql, params=None: statements.append(sql) or []
    assert repo.resolve_patient_session("temporary-token") is None
    sql = statements[0]
    assert "NOT usada" in sql
    assert "revogada_em IS NULL" in sql
    assert "expires_at>CURRENT_TIMESTAMP()" in sql


def test_consuming_patient_session_marks_it_used():
    repo = repository()
    statements = []
    repo._query = lambda sql, params=None: statements.append(sql) or []
    repo.consume_patient_session("temporary-token")
    assert "SET usada=TRUE" in statements[0]


def test_revoking_patient_session_invalidates_only_active_unused_session():
    repo = repository()
    statements = []
    repo._query = lambda sql, params=None: statements.append(sql) or []
    repo.revoke_patient_session("temporary-token")
    sql = statements[0]
    assert "SET revogada_em=CURRENT_TIMESTAMP()" in sql
    assert "AND NOT usada" in sql
    assert "revogada_em IS NULL" in sql


def test_evidence_hmac_is_deterministic_and_does_not_expose_value(monkeypatch):
    repo = repository()
    monkeypatch.setattr("app.repositories.mvp.settings.evidence_hmac_secret", "test-secret")
    first = repo._evidence_digest("192.0.2.1")
    assert first == repo._evidence_digest("192.0.2.1")
    assert first != "192.0.2.1"
    assert len(first) == 64
