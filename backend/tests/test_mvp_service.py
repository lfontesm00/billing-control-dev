from datetime import UTC, date, datetime, timedelta

import pytest

from app.core import BusinessError, CurrentUser
from app.models.mvp import AcceptanceInput, AnamnesisSubmit, AnswerInput, ClinicCreate, GuardianInput, PatientCreate, TeamMemberCreate
from pydantic import ValidationError
from app.services.mvp import MvpService, age_on, anamnesis_status, form_is_available


class FakeRepository:
    def __init__(self):
        self.identity={"id_usuario":1,"id_organizacao":10,"ativo":True}; self.permissions=True; self.clinic_count=0; self.patient=None; self.linked=False
        self.form={"id_formulario":30,"versao":1,"termos_versao":"terms-v1","status":"PUBLICADO","validado_clinicamente":True,"questions":[{"id_pergunta":31,"obrigatoria":True}]}; self.idempotent_result=None
    def resolve_identity(self,user): return self.identity
    def bootstrap(self,user,name): return {"id_organizacao":10,"nome":name}
    def has_permission(self,*args): return self.permissions
    def count_organization_clinics(self,_id): return self.clinic_count
    def create_clinic(self,org,data,actor): return {"id_clinica":20,**data}
    def get_patient_by_cpf(self,cpf): return self.patient
    def has_patient_link(self,*args): return self.linked
    def create_patient_with_link(self,clinic,data,actor): return {"id_paciente":40,"id_clinica":clinic}
    def get_create_patient_result(self,key): return self.idempotent_result
    def link_patient(self,patient,clinic,actor): return {"id_paciente":patient,"id_clinica":clinic}
    def get_form(self,clinic): return self.form
    def submit_anamnesis(self,clinic,patient,data,actor): self.submitted=data; return {"status":"ATUALIZADA","numero_versao":1}


@pytest.fixture
def context():
    repo=FakeRepository(); return repo,MvpService(repo),CurrentUser("uid","owner@example.com")


def patient(**changes):
    data={"nome":"Maria da Silva","cpf":"52998224725","data_nascimento":date(1990,1,1),"sexo":"FEMININO","idempotency_key":"request-123"}; data.update(changes); return PatientCreate(**data)


def test_age_accounts_for_birthday():
    assert age_on(date(2008,8,22),date(2026,8,21))==17
    assert age_on(date(2008,8,21),date(2026,8,21))==18


def test_anamnesis_expires_after_one_year():
    now=datetime(2026,8,21,tzinfo=UTC)
    assert anamnesis_status(None,now)=="PENDENTE"
    assert anamnesis_status(now-timedelta(days=200),now)=="ATUALIZADA"
    assert anamnesis_status(now.replace(year=2025),now)=="VENCIDA"


def test_clinic_limit_is_global_to_organization(context):
    repo,svc,user=context; repo.clinic_count=3
    with pytest.raises(BusinessError,match="três clínicas") as error:
        svc.create_clinic(user,ClinicCreate(nome="Clínica A",razao_social="Clínica A Ltda",cnpj_cpf="11222333000181",email="a@clinic.com"))
    assert error.value.code=="CLINIC_LIMIT_REACHED"


def test_minor_requires_guardian(context):
    _,svc,user=context
    with pytest.raises(BusinessError) as error: svc.create_patient(user,20,patient(data_nascimento=date.today().replace(year=date.today().year-10)))
    assert error.value.code=="GUARDIAN_REQUIRED"


def test_minor_rejects_guardian_with_invalid_cpf(context):
    _,svc,user=context
    guardian=GuardianInput(nome="Responsável Teste",cpf="11111111111",telefone="81999999999",parentesco="PAI")
    with pytest.raises(BusinessError) as error:
        svc.create_patient(user,20,patient(data_nascimento=date.today().replace(year=date.today().year-10),responsavel=guardian))
    assert error.value.code=="GUARDIAN_REQUIRED"


def test_existing_global_patient_returns_opaque_conflict(context):
    repo,svc,user=context; repo.patient={"id_paciente":99}; repo.linked=False
    with pytest.raises(BusinessError) as error: svc.create_patient(user,20,patient())
    assert error.value.code=="PATIENT_EXISTS_NOT_LINKED"
    assert error.value.context=={}


def test_repeated_idempotency_key_returns_original_result_before_cpf_conflict(context):
    repo,svc,user=context
    repo.idempotent_result={"id_paciente":40,"id_clinica":20}
    repo.patient={"id_paciente":40}; repo.linked=True
    assert svc.create_patient(user,20,patient())=={"id_paciente":40,"id_clinica":20}


def test_permission_is_enforced(context):
    repo,svc,user=context; repo.permissions=False
    with pytest.raises(BusinessError) as error: svc.create_patient(user,20,patient())
    assert error.value.status_code==403


def test_temporary_password_blocks_business_operations(context):
    repo,svc,user=context; repo.identity["troca_senha_obrigatoria"]=True
    with pytest.raises(BusinessError) as error: svc.identity(user)
    assert error.value.code=="PASSWORD_CHANGE_REQUIRED"
    assert svc.identity(user,allow_password_change=True)["id_usuario"]==1


def test_team_member_model_rejects_full_access():
    with pytest.raises(ValidationError):
        TeamMemberCreate(nome="Administrador indevido",email="admin@example.com",profile_code="FULL_ACCESS",clinic_ids=[1])


def test_anamnesis_requires_clinically_validated_form(context):
    repo,svc,user=context; repo.form["validado_clinicamente"]=False
    payload=AnamnesisSubmit(answers=[AnswerInput(question_id=31,value=True)],acceptance=AcceptanceInput(nome="Maria",cpf="52998224725",termos_aceitos=True),idempotency_key="submit-123")
    with pytest.raises(BusinessError) as error: svc.submit_anamnesis(user,20,40,payload)
    assert error.value.code=="NO_VALIDATED_FORM"


def test_test_form_is_blocked_when_setting_is_disabled():
    form={"status":"PUBLICADO_TESTE","validado_clinicamente":False}
    assert form_is_available(form,allow_test=False) is False


def test_test_form_is_allowed_only_when_explicitly_enabled():
    form={"status":"PUBLICADO_TESTE","validado_clinicamente":False}
    assert form_is_available(form,allow_test=True) is True
    assert form_is_available({**form,"validado_clinicamente":True},allow_test=True) is False


def test_unvalidated_production_form_is_always_blocked():
    assert form_is_available({"status":"PUBLICADO","validado_clinicamente":False},allow_test=True) is False


def test_required_anamnesis_answers(context):
    _,svc,user=context
    payload=AnamnesisSubmit(answers=[],acceptance=AcceptanceInput(nome="Maria",cpf="52998224725",termos_aceitos=True),idempotency_key="submit-123")
    with pytest.raises(BusinessError) as error: svc.submit_anamnesis(user,20,40,payload)
    assert error.value.code=="REQUIRED_ANSWERS_MISSING"


def test_hidden_conditional_question_is_not_required(context):
    repo,svc,user=context
    repo.form["questions"]=[
        {"id_pergunta":31,"obrigatoria":True},
        {"id_pergunta":32,"obrigatoria":True,"parent_question_id":31,"show_when_value":"true"},
    ]
    payload=AnamnesisSubmit(answers=[AnswerInput(question_id=31,value=False)],acceptance=AcceptanceInput(nome="Maria",cpf="52998224725",termos_aceitos=True),idempotency_key="submit-123")
    assert svc.submit_anamnesis(user,20,40,payload)["status"]=="ATUALIZADA"


def test_visible_conditional_question_is_required(context):
    repo,svc,user=context
    repo.form["questions"]=[
        {"id_pergunta":31,"obrigatoria":True},
        {"id_pergunta":32,"obrigatoria":True,"parent_question_id":31,"show_when_value":"true"},
    ]
    payload=AnamnesisSubmit(answers=[AnswerInput(question_id=31,value=True)],acceptance=AcceptanceInput(nome="Maria",cpf="52998224725",termos_aceitos=True),idempotency_key="submit-123")
    with pytest.raises(BusinessError) as error: svc.submit_anamnesis(user,20,40,payload)
    assert error.value.code=="REQUIRED_ANSWERS_MISSING"
    assert error.value.context=={"question_ids":[32]}


def test_submission_uses_terms_version_from_form(context):
    repo,svc,user=context
    payload=AnamnesisSubmit(answers=[AnswerInput(question_id=31,value=True)],acceptance=AcceptanceInput(nome="Maria",cpf="52998224725",termos_aceitos=True),idempotency_key="submit-terms")
    svc.submit_anamnesis(user,20,40,payload)
    assert repo.submitted["form_version"]==1
    assert repo.submitted["terms_version"]=="terms-v1"
