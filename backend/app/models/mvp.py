from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.utils.identifiers import digits, normalize_email, normalize_phone


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def clean_text(value):
    return value.strip() if isinstance(value, str) else value


class OrganizationCreate(ApiModel):
    nome: str = Field(min_length=2, max_length=255)


class ClinicCreate(ApiModel):
    nome: str = Field(min_length=2, max_length=255)
    razao_social: str = Field(min_length=2, max_length=255)
    cnpj_cpf: str
    email: str
    telefone: str | None = None
    endereco: str | None = None
    responsavel: str | None = None
    cro_responsavel: str | None = None

    @field_validator("cnpj_cpf", mode="before")
    @classmethod
    def normalize_document(cls, value: str) -> str:
        return digits(value)

    @field_validator("email", mode="before")
    @classmethod
    def email_lower(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("telefone", mode="before")
    @classmethod
    def normalize_tel(cls, value):
        return normalize_phone(value)

    @field_validator("nome", "razao_social", "endereco", "responsavel", "cro_responsavel", mode="before")
    @classmethod
    def strip_text(cls, value):
        return clean_text(value)


class InviteCreate(ApiModel):
    email: str
    profile_code: str
    clinic_ids: list[int] = Field(min_length=1)

    @field_validator("email", mode="before")
    @classmethod
    def email_lower(cls, value: str) -> str:
        return normalize_email(value)


class TeamMemberCreate(ApiModel):
    nome: str = Field(min_length=2, max_length=255)
    email: str
    profile_code: Literal["RECEPCAO", "FINANCEIRO"]
    clinic_ids: list[int] = Field(min_length=1)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_member_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("nome", mode="before")
    @classmethod
    def normalize_member_name(cls, value: str) -> str:
        return clean_text(value)


class TeamMemberUpdate(ApiModel):
    nome: str = Field(min_length=2, max_length=255)
    profile_code: Literal["RECEPCAO", "FINANCEIRO"]
    clinic_ids: list[int] = Field(min_length=1)

    @field_validator("nome", mode="before")
    @classmethod
    def normalize_updated_member_name(cls, value: str) -> str:
        return clean_text(value)


class PasswordChange(ApiModel):
    nova_senha: str = Field(min_length=8, max_length=128)


class GuardianInput(ApiModel):
    nome: str = Field(min_length=2, max_length=255)
    cpf: str
    telefone: str
    email: str | None = None
    parentesco: str = Field(min_length=2, max_length=50)

    @field_validator("cpf", mode="before")
    @classmethod
    def normalize_cpf(cls, value: str) -> str:
        return digits(value)

    @field_validator("telefone", mode="before")
    @classmethod
    def normalize_tel(cls, value):
        return normalize_phone(value)

    @field_validator("email", mode="before")
    @classmethod
    def email_lower(cls, value):
        return normalize_email(value) if value else None

    @field_validator("nome", "parentesco", mode="before")
    @classmethod
    def strip_text(cls, value):
        return clean_text(value)


class PatientCreate(ApiModel):
    nome: str = Field(min_length=2, max_length=255)
    cpf: str
    data_nascimento: date
    sexo: str = "NAO_INFORMADO"
    telefone: str | None = None
    email: str | None = None
    endereco: str | None = None
    plano_odontologico: str | None = None
    responsavel: GuardianInput | None = None
    idempotency_key: str = Field(min_length=8, max_length=100)

    @field_validator("cpf", mode="before")
    @classmethod
    def normalize_cpf(cls, value: str) -> str:
        return digits(value)

    @field_validator("telefone", mode="before")
    @classmethod
    def normalize_tel(cls, value):
        return normalize_phone(value)

    @field_validator("email", mode="before")
    @classmethod
    def email_lower(cls, value):
        return normalize_email(value) if value else None

    @field_validator("nome", "sexo", "endereco", "plano_odontologico", mode="before")
    @classmethod
    def strip_text(cls, value):
        return clean_text(value)


class PatientUpdate(ApiModel):
    nome: str | None = Field(default=None, min_length=2, max_length=255)
    telefone: str | None = None
    email: str | None = None
    endereco: str | None = None
    plano_odontologico: str | None = None
    responsavel: GuardianInput | None = None


class QuestionType(StrEnum):
    BOOLEAN = "BOOLEAN"
    TEXT = "TEXT"
    SINGLE_CHOICE = "SINGLE_CHOICE"


class AnswerInput(ApiModel):
    question_id: int
    value: bool | str | None


class AcceptanceInput(ApiModel):
    nome: str = Field(min_length=2, max_length=255)
    cpf: str
    termos_aceitos: Literal[True]

    @field_validator("cpf", mode="before")
    @classmethod
    def normalize_cpf(cls, value: str) -> str:
        return digits(value)


class AnamnesisSubmit(ApiModel):
    answers: list[AnswerInput]
    acceptance: AcceptanceInput
    idempotency_key: str = Field(min_length=8, max_length=100)


class ProfessionalApproval(ApiModel):
    nome_profissional: str = Field(min_length=2, max_length=255)
    cro_profissional: str = Field(min_length=3, max_length=50)
    declaracao_confirmada: Literal[True]

    @field_validator("nome_profissional", "cro_profissional", mode="before")
    @classmethod
    def strip_professional_fields(cls, value):
        return clean_text(value)


class PatientSessionCreate(ApiModel):
    patient_id: int


class RemotePatientSessionCreate(ApiModel):
    patient_id: int
    canal_compartilhamento: Literal["COPY", "WHATSAPP", "EMAIL"] = "COPY"


class RemoteIdentityVerify(ApiModel):
    cpf: str
    data_nascimento: date

    @field_validator("cpf", mode="before")
    @classmethod
    def normalize_cpf(cls, value: str) -> str:
        return digits(value)


class PatientSessionResponse(ApiModel):
    token: str
    expires_at: datetime


class PatientSummary(ApiModel):
    id_paciente: int
    nome: str
    cpf_mascarado: str
    telefone: str | None = None
    ativo: bool = True
    anamnese_status: str = "PENDENTE"


class PaginatedPatients(ApiModel):
    items: list[PatientSummary]
    page: int
    page_size: int
    total: int


class ProfileResponse(ApiModel):
    patient: dict[str, Any]
    guardian: dict[str, Any] | None = None
    anamnesis_status: str
    alerts: list[dict[str, Any]]


class DoctorListItem(ApiModel):
    id_doutor: int
    id_doutor_clinica: int | None = None
    nome_doutor: str
    especialidade: str | None = None
    cro: str | None = None
    cro_estado: str | None = None
    percentual_repasse: float | None = None
    flag_ativo: bool = True
    total_consultas: int = 0


class PaginatedDoctors(ApiModel):
    items: list[DoctorListItem]
    page: int
    page_size: int
    total: int


class DoctorDetail(DoctorListItem):
    id_clinica: int
    data_inicio: datetime | None = None
    data_fim: date | None = None
