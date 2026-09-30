from datetime import UTC, date, datetime, timedelta
from typing import Protocol

from app.core import BusinessError, CurrentUser
from app.config import settings
from app.models.mvp import AnamnesisSubmit, ClinicCreate, PatientCreate
from app.utils.identifiers import is_valid_cnpj, is_valid_cpf


class MvpRepository(Protocol):
    def bootstrap(self, user: CurrentUser, organization_name: str) -> dict: ...
    def resolve_identity(self, user: CurrentUser) -> dict | None: ...
    def list_clinics(self, firebase_uid: str) -> list[dict]: ...
    def count_organization_clinics(self, organization_id: int) -> int: ...
    def create_clinic(self, organization_id: int, data: dict, actor_id: int) -> dict: ...
    def has_permission(self, user_id: int, clinic_id: int | None, permission: str) -> bool: ...
    def create_patient_with_link(self, clinic_id: int, data: dict, actor_id: int) -> dict: ...
    def get_create_patient_result(self, idempotency_key: str) -> dict | None: ...
    def get_patient_by_cpf(self, cpf: str) -> dict | None: ...
    def has_patient_link(self, patient_id: int, clinic_id: int) -> bool: ...
    def link_patient(self, patient_id: int, clinic_id: int, actor_id: int) -> dict: ...
    def get_form(self, clinic_id: int) -> dict | None: ...
    def submit_anamnesis(self, clinic_id: int, patient_id: int, data: dict, actor_id: int | None) -> dict: ...
    def list_doctors(self, clinic_id: int, search: str, active: bool | None, page: int, page_size: int) -> dict: ...
    def get_doctor(self, clinic_id: int, doctor_id: int) -> dict | None: ...


def age_on(birth_date: date, today: date | None = None) -> int:
    current = today or date.today()
    return current.year - birth_date.year - ((current.month, current.day) < (birth_date.month, birth_date.day))


def anamnesis_status(accepted_at: datetime | None, now: datetime | None = None) -> str:
    if accepted_at is None:
        return "PENDENTE"
    current = now or datetime.now(UTC)
    if accepted_at.tzinfo is None:
        accepted_at = accepted_at.replace(tzinfo=UTC)
    try:
        expires = accepted_at.replace(year=accepted_at.year + 1)
    except ValueError:
        expires = accepted_at.replace(year=accepted_at.year + 1, day=28)
    return "VENCIDA" if current >= expires else "ATUALIZADA"


def form_is_available(form: dict | None, allow_test: bool | None = None) -> bool:
    if not form:
        return False
    if form.get("status") == "PUBLICADO" and form.get("validado_clinicamente") is True:
        return True
    test_enabled = settings.allow_unvalidated_test_forms if allow_test is None else allow_test
    return bool(test_enabled and form.get("status") == "PUBLICADO_TESTE" and form.get("validado_clinicamente") is False)


def question_is_visible(question: dict, answers: dict[int, object]) -> bool:
    parent = question.get("parent_question_id")
    if parent is None:
        return True
    if parent not in answers:
        return False
    return str(answers[parent]).strip().lower() == str(question.get("show_when_value", "")).strip().lower()


class MvpService:
    def __init__(self, repository: MvpRepository):
        self.repository = repository

    def identity(self, user: CurrentUser, allow_password_change: bool = False) -> dict:
        identity = self.repository.resolve_identity(user)
        if not identity:
            raise BusinessError("SETUP_REQUIRED", "Usuário ainda não pertence a uma organização", 404)
        if not identity.get("ativo", True):
            raise BusinessError("USER_INACTIVE", "Usuário inativo", 403)
        if identity.get("troca_senha_obrigatoria") and not allow_password_change:
            raise BusinessError("PASSWORD_CHANGE_REQUIRED", "Troque a senha temporária antes de continuar", 403)
        return identity

    def bootstrap(self, user: CurrentUser, name: str) -> dict:
        if self.repository.resolve_identity(user):
            raise BusinessError("ORGANIZATION_EXISTS", "Usuário já pertence a uma organização", 409)
        return self.repository.bootstrap(user, name.strip())

    def create_clinic(self, user: CurrentUser, data: ClinicCreate) -> dict:
        identity = self.identity(user)
        if not self.repository.has_permission(identity["id_usuario"], None, "CLINIC_MANAGE"):
            raise BusinessError("FORBIDDEN", "Sem permissão para gerenciar clínicas", 403)
        if self.repository.count_organization_clinics(identity["id_organizacao"]) >= 3:
            raise BusinessError("CLINIC_LIMIT_REACHED", "A organização já possui três clínicas", 409)
        if not (is_valid_cpf(data.cnpj_cpf) or is_valid_cnpj(data.cnpj_cpf)):
            raise BusinessError("INVALID_DOCUMENT", "CPF/CNPJ inválido", 422)
        return self.repository.create_clinic(identity["id_organizacao"], data.model_dump(), identity["id_usuario"])

    def create_patient(self, user: CurrentUser, clinic_id: int, data: PatientCreate) -> dict:
        identity = self.identity(user)
        self._authorize(identity, clinic_id, "PATIENT_WRITE")
        if not is_valid_cpf(data.cpf):
            raise BusinessError("INVALID_CPF", "CPF inválido", 422)
        if age_on(data.data_nascimento) < 18:
            if not data.responsavel or not is_valid_cpf(data.responsavel.cpf):
                raise BusinessError("GUARDIAN_REQUIRED", "Responsável legal válido é obrigatório para menor", 422)
        cached = self.repository.get_create_patient_result(data.idempotency_key)
        if cached:
            return cached
        existing = self.repository.get_patient_by_cpf(data.cpf)
        if existing:
            if self.repository.has_patient_link(existing["id_paciente"], clinic_id):
                raise BusinessError("PATIENT_ALREADY_LINKED", "Paciente já está vinculado à clínica", 409)
            raise BusinessError("PATIENT_EXISTS_NOT_LINKED", "Paciente já possui cadastro e pode ser vinculado", 409)
        try:
            return self.repository.create_patient_with_link(clinic_id, data.model_dump(mode="json"), identity["id_usuario"])
        except ValueError as exc:
            if str(exc) == "PATIENT_DUPLICATE":
                raise BusinessError("PATIENT_ALREADY_LINKED", "Já existe um paciente com este CPF nesta clínica", 409) from exc
            if str(exc) == "IDEMPOTENCY_CONFLICT":
                raise BusinessError("IDEMPOTENCY_CONFLICT", "Esta solicitação já foi processada", 409) from exc
            if str(exc) == "CLINIC_NOT_FOUND":
                raise BusinessError("CLINIC_NOT_FOUND", "Clínica não encontrada", 404) from exc
            raise

    def link_patient(self, user: CurrentUser, clinic_id: int, patient_id: int) -> dict:
        identity = self.identity(user)
        self._authorize(identity, clinic_id, "PATIENT_WRITE")
        return self.repository.link_patient(patient_id, clinic_id, identity["id_usuario"])

    def submit_anamnesis(self, user: CurrentUser | None, clinic_id: int, patient_id: int, payload: AnamnesisSubmit, patient_session: bool = False, form_id: int | None = None) -> dict:
        identity = None if patient_session else self.identity(user)  # type: ignore[arg-type]
        if identity:
            self._authorize(identity, clinic_id, "ANAMNESIS_WRITE")
        if not is_valid_cpf(payload.acceptance.cpf):
            raise BusinessError("INVALID_ACCEPTANCE_CPF", "CPF do aceite é inválido", 422)
        form = self.repository.get_form_by_id(form_id) if form_id else self.repository.get_form(clinic_id)
        if not form_is_available(form):
            raise BusinessError("NO_VALIDATED_FORM", "Não há formulário clinicamente validado e publicado", 409)
        answers = {item.question_id: item.value for item in payload.answers}
        missing = [q["id_pergunta"] for q in form["questions"] if q.get("obrigatoria") and question_is_visible(q, answers) and q["id_pergunta"] not in answers]
        if missing:
            raise BusinessError("REQUIRED_ANSWERS_MISSING", "Existem perguntas obrigatórias sem resposta", 422, {"question_ids": missing})
        data = payload.model_dump(mode="json") | {
            "form_id": form["id_formulario"],
            "form_version": form["versao"],
            "terms_version": form["termos_versao"],
        }
        return self.repository.submit_anamnesis(clinic_id, patient_id, data, identity["id_usuario"] if identity else None)

    def list_doctors(self, user: CurrentUser, clinic_id: int, search: str = "", active: bool | None = None, page: int = 1, page_size: int = 25) -> dict:
        identity = self.identity(user)
        self._authorize(identity, clinic_id, "DOCTOR_READ")
        return self.repository.list_doctors(clinic_id, search, active, page, page_size)

    def get_doctor(self, user: CurrentUser, clinic_id: int, doctor_id: int) -> dict:
        identity = self.identity(user)
        self._authorize(identity, clinic_id, "DOCTOR_READ")
        doctor = self.repository.get_doctor(clinic_id, doctor_id)
        if not doctor:
            raise BusinessError("DOCTOR_NOT_FOUND", "Doutor não encontrado nesta clínica", 404)
        return doctor

    def _authorize(self, identity: dict, clinic_id: int, permission: str) -> None:
        if not self.repository.has_permission(identity["id_usuario"], clinic_id, permission):
            raise BusinessError("FORBIDDEN", "Sem permissão para esta clínica", 403)
