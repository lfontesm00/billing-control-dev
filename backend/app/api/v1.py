from functools import lru_cache
import secrets

from fastapi import APIRouter, Depends, Header, Query, Request, status

from app.config import settings
from app.core import BusinessError, CurrentUser, create_firebase_user, delete_firebase_user, get_current_user, reset_firebase_password
from app.models.mvp import AnamnesisSubmit, ClinicCreate, InviteCreate, OrganizationCreate, PasswordChange, PatientCreate, PatientSessionCreate, ProfessionalApproval, RemoteIdentityVerify, RemotePatientSessionCreate, TeamMemberCreate, TeamMemberUpdate, PaginatedDoctors, DoctorDetail
from app.services.mvp import anamnesis_status, form_is_available
from app.repositories.mvp import BigQueryMvpRepository
from app.services.mvp import MvpService

router = APIRouter(prefix=settings.api_prefix)


@lru_cache
def repository() -> BigQueryMvpRepository:
    return BigQueryMvpRepository()


def service(repo: BigQueryMvpRepository = Depends(repository)) -> MvpService:
    return MvpService(repo)


@router.post("/setup", status_code=status.HTTP_201_CREATED, tags=["autenticacao"])
def setup(payload: OrganizationCreate, user: CurrentUser = Depends(get_current_user), svc: MvpService = Depends(service)):
    return svc.bootstrap(user, payload.nome)


@router.get("/me", tags=["autenticacao"])
def me(user: CurrentUser = Depends(get_current_user), svc: MvpService = Depends(service)):
    return svc.identity(user, allow_password_change=True)


@router.post("/me/alterar-senha", tags=["autenticacao"])
def password_changed(payload: PasswordChange, user: CurrentUser = Depends(get_current_user), svc: MvpService = Depends(service), repo: BigQueryMvpRepository = Depends(repository)):
    identity = svc.identity(user, allow_password_change=True)
    if not identity.get("troca_senha_obrigatoria"):
        raise BusinessError("PASSWORD_CHANGE_NOT_REQUIRED", "Esta conta não possui troca obrigatória pendente", 409)
    try: reset_firebase_password(user.firebase_uid, payload.nova_senha)
    except Exception as exc: raise BusinessError("PASSWORD_CHANGE_FAILED", "Não foi possível alterar a senha", 409) from exc
    repo.confirm_password_changed(identity["id_usuario"])
    return {"troca_senha_obrigatoria": False}


@router.get("/me/clinicas", tags=["autenticacao"])
def my_clinics(user: CurrentUser = Depends(get_current_user), repo: BigQueryMvpRepository = Depends(repository)):
    identity = repo.resolve_identity(user)
    if not identity or not identity.get("ativo", True): raise BusinessError("USER_INACTIVE", "Usuário inativo", 403)
    if identity.get("troca_senha_obrigatoria"): raise BusinessError("PASSWORD_CHANGE_REQUIRED", "Troque a senha temporária antes de continuar", 403)
    return repo.list_clinics(user.firebase_uid)


@router.post("/clinicas", status_code=status.HTTP_201_CREATED, tags=["clinicas"])
def create_clinic(payload: ClinicCreate, user: CurrentUser = Depends(get_current_user), svc: MvpService = Depends(service)):
    return svc.create_clinic(user, payload)


@router.get("/perfis", tags=["administracao"])
def profiles(user: CurrentUser = Depends(get_current_user), svc: MvpService = Depends(service), repo: BigQueryMvpRepository = Depends(repository)):
    identity=svc.identity(user)
    if not repo.has_permission(identity["id_usuario"],None,"USER_MANAGE"): raise BusinessError("FORBIDDEN","Sem permissão para gerenciar usuários",403)
    return repo.list_profiles()


@router.post("/convites", status_code=status.HTTP_201_CREATED, tags=["administracao"])
def invite(payload: InviteCreate, user: CurrentUser = Depends(get_current_user), svc: MvpService = Depends(service), repo: BigQueryMvpRepository = Depends(repository)):
    identity=svc.identity(user)
    if not repo.has_permission(identity["id_usuario"],None,"USER_MANAGE"): raise BusinessError("FORBIDDEN","Sem permissão para gerenciar usuários",403)
    if payload.profile_code not in {"RECEPCAO","FINANCEIRO"}: raise BusinessError("INVALID_TEAM_PROFILE","Somente os perfis RECEPCAO e FINANCEIRO podem ser atribuídos",422)
    if repo.count_active_team_members(identity["id_organizacao"]) >= 2: raise BusinessError("TEAM_MEMBER_LIMIT_REACHED","A organização já possui dois colaboradores ativos",409)
    allowed={c["id_clinica"] for c in repo.list_clinics(user.firebase_uid)}
    if not set(payload.clinic_ids).issubset(allowed): raise BusinessError("INVALID_CLINICS","Uma ou mais clínicas não pertencem à organização",422)
    try: return repo.create_invite(identity["id_organizacao"],payload.model_dump(),identity["id_usuario"])
    except ValueError as exc: raise BusinessError(str(exc),"Não foi possível criar o convite",409) from exc


def _team_admin(user: CurrentUser, svc: MvpService, repo: BigQueryMvpRepository) -> dict:
    identity = svc.identity(user)
    if not repo.has_permission(identity["id_usuario"], None, "USER_MANAGE"):
        raise BusinessError("FORBIDDEN", "Sem permissão para gerenciar a equipe", 403)
    return identity


def _validate_member_clinics(user: CurrentUser, clinic_ids: list[int], repo: BigQueryMvpRepository) -> None:
    allowed = {item["id_clinica"] for item in repo.list_clinics(user.firebase_uid)}
    if not set(clinic_ids).issubset(allowed):
        raise BusinessError("INVALID_CLINICS", "Uma ou mais clínicas não pertencem à organização", 422)


def _translate_team_error(exc: Exception) -> BusinessError:
    message = str(exc)
    if "TEAM_MEMBER_LIMIT_REACHED" in message:
        return BusinessError("TEAM_MEMBER_LIMIT_REACHED", "A organização já possui dois colaboradores ativos", 409)
    if "EMAIL_ALREADY_EXISTS" in message or "EMAIL_EXISTS" in message or "email-already-exists" in message:
        return BusinessError("TEAM_MEMBER_EMAIL_EXISTS", "Este e-mail já possui uma conta", 409)
    if "TEAM_MEMBER_NOT_FOUND" in message:
        return BusinessError("TEAM_MEMBER_NOT_FOUND", "Colaborador não encontrado", 404)
    return BusinessError("TEAM_MEMBER_OPERATION_FAILED", "Não foi possível concluir a operação de equipe", 409)


def _temporary_password() -> str:
    return f"Bc!{secrets.token_urlsafe(12)}"


@router.get("/equipe", tags=["administracao"])
def team(user: CurrentUser = Depends(get_current_user), svc: MvpService = Depends(service), repo: BigQueryMvpRepository = Depends(repository)):
    identity = _team_admin(user, svc, repo)
    members = repo.list_team_members(identity["id_organizacao"])
    return {"items": members, "ativos": sum(1 for item in members if item["ativo"]), "limite": 2}


@router.post("/equipe", status_code=status.HTTP_201_CREATED, tags=["administracao"])
def create_team_member(payload: TeamMemberCreate, user: CurrentUser = Depends(get_current_user), svc: MvpService = Depends(service), repo: BigQueryMvpRepository = Depends(repository)):
    identity = _team_admin(user, svc, repo)
    _validate_member_clinics(user, payload.clinic_ids, repo)
    if repo.count_active_team_members(identity["id_organizacao"]) >= 2:
        raise BusinessError("TEAM_MEMBER_LIMIT_REACHED", "A organização já possui dois colaboradores ativos", 409)
    password = _temporary_password()
    firebase_user = None
    try:
        firebase_user = create_firebase_user(payload.email, password, payload.nome)
        result = repo.create_team_member(identity["id_organizacao"], firebase_user.uid, payload.model_dump(), identity["id_usuario"])
    except Exception as exc:
        if firebase_user:
            try: delete_firebase_user(firebase_user.uid)
            except Exception: pass
        raise _translate_team_error(exc) from exc
    return {**result, "senha_temporaria": password}


@router.put("/equipe/{member_id}", tags=["administracao"])
def update_team_member(member_id: int, payload: TeamMemberUpdate, user: CurrentUser = Depends(get_current_user), svc: MvpService = Depends(service), repo: BigQueryMvpRepository = Depends(repository)):
    identity = _team_admin(user, svc, repo)
    _validate_member_clinics(user, payload.clinic_ids, repo)
    try: return repo.update_team_member(identity["id_organizacao"], member_id, payload.model_dump(), identity["id_usuario"])
    except Exception as exc: raise _translate_team_error(exc) from exc


@router.post("/equipe/{member_id}/inativar", tags=["administracao"])
def inactivate_team_member(member_id: int, user: CurrentUser = Depends(get_current_user), svc: MvpService = Depends(service), repo: BigQueryMvpRepository = Depends(repository)):
    identity = _team_admin(user, svc, repo)
    try: return repo.set_team_member_active(identity["id_organizacao"], member_id, False, identity["id_usuario"])
    except Exception as exc: raise _translate_team_error(exc) from exc


@router.post("/equipe/{member_id}/reativar", tags=["administracao"])
def reactivate_team_member(member_id: int, user: CurrentUser = Depends(get_current_user), svc: MvpService = Depends(service), repo: BigQueryMvpRepository = Depends(repository)):
    identity = _team_admin(user, svc, repo)
    if repo.count_active_team_members(identity["id_organizacao"]) >= 2:
        raise BusinessError("TEAM_MEMBER_LIMIT_REACHED", "A organização já possui dois colaboradores ativos", 409)
    try: return repo.set_team_member_active(identity["id_organizacao"], member_id, True, identity["id_usuario"])
    except Exception as exc: raise _translate_team_error(exc) from exc


@router.post("/equipe/{member_id}/redefinir-senha", tags=["administracao"])
def reset_team_member_password(member_id: int, user: CurrentUser = Depends(get_current_user), svc: MvpService = Depends(service), repo: BigQueryMvpRepository = Depends(repository)):
    identity = _team_admin(user, svc, repo)
    member = repo.get_team_member(identity["id_organizacao"], member_id)
    if not member: raise BusinessError("TEAM_MEMBER_NOT_FOUND", "Colaborador não encontrado", 404)
    if not member.get("firebase_uid"): raise BusinessError("TEAM_MEMBER_FIREBASE_MISSING", "Conta Firebase do colaborador não encontrada", 409)
    password = _temporary_password()
    try:
        repo.mark_temporary_password(identity["id_organizacao"], member_id, identity["id_usuario"])
        reset_firebase_password(member["firebase_uid"], password)
    except Exception as exc: raise _translate_team_error(exc) from exc
    return {"id_usuario": member_id, "senha_temporaria": password, "troca_senha_obrigatoria": True}


ANAMNESIS_STATUSES = {"PENDENTE", "PENDENTE_APROVACAO", "VENCIDA", "ATUALIZADA"}


def _mask_patient_cpf(item: dict) -> dict:
    cpf = item.pop("cpf", "")
    item["cpf_mascarado"] = f"***.{cpf[3:6]}.{cpf[6:9]}-**" if len(cpf) == 11 else "***"
    return item


@router.get("/clinicas/{clinic_id}/painel", tags=["pacientes"])
def clinic_panel(clinic_id: int, user: CurrentUser = Depends(get_current_user), svc: MvpService = Depends(service), repo: BigQueryMvpRepository = Depends(repository)):
    identity = svc.identity(user)
    svc._authorize(identity, clinic_id, "PATIENT_READ")
    result = repo.clinic_panel(clinic_id)
    result["prioridades"] = [_mask_patient_cpf(item) for item in result.get("prioridades", [])]
    return result


@router.get("/clinicas/{clinic_id}/pacientes", tags=["pacientes"])
def patients(clinic_id: int, search: str = "", active: bool | None = None, anamnesis_status: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), user: CurrentUser = Depends(get_current_user), svc: MvpService = Depends(service), repo: BigQueryMvpRepository = Depends(repository)):
    identity = svc.identity(user)
    svc._authorize(identity, clinic_id, "PATIENT_READ")
    if anamnesis_status is not None and anamnesis_status not in ANAMNESIS_STATUSES:
        raise BusinessError("INVALID_ANAMNESIS_STATUS", "Situação de anamnese inválida", 422)
    result = repo.list_patients(clinic_id, search.strip(), active, page, page_size, anamnesis_status)
    result["items"] = [_mask_patient_cpf(item) for item in result["items"]]
    return result


@router.post("/clinicas/{clinic_id}/pacientes", status_code=status.HTTP_201_CREATED, tags=["pacientes"])
def create_patient(clinic_id: int, payload: PatientCreate, user: CurrentUser = Depends(get_current_user), svc: MvpService = Depends(service)):
    return svc.create_patient(user, clinic_id, payload)


@router.post("/clinicas/{clinic_id}/pacientes/{patient_id}/vinculo", status_code=status.HTTP_201_CREATED, tags=["pacientes"])
def link_patient(clinic_id: int, patient_id: int, user: CurrentUser = Depends(get_current_user), svc: MvpService = Depends(service)):
    return svc.link_patient(user, clinic_id, patient_id)


@router.get("/clinicas/{clinic_id}/pacientes/{patient_id}", tags=["pacientes"])
def patient_profile(clinic_id:int,patient_id:int,user:CurrentUser=Depends(get_current_user),svc:MvpService=Depends(service),repo:BigQueryMvpRepository=Depends(repository)):
    identity=svc.identity(user);svc._authorize(identity,clinic_id,"PATIENT_READ");profile=repo.patient_profile(clinic_id,patient_id)
    if not profile: raise BusinessError("PATIENT_NOT_FOUND","Paciente não encontrado nesta clínica",404)
    profile["id_clinica"]=clinic_id
    latest=profile.get("latest_anamnesis")
    profile["anamnese_status"]="PENDENTE_APROVACAO" if latest and latest.get("status_aprovacao")!="APROVADA" else anamnesis_status(latest.get("aceito_em") if latest else None)
    return profile


@router.get("/clinicas/{clinic_id}/pacientes/{patient_id}/anamnese/historico", tags=["anamnese"])
def history(clinic_id:int,patient_id:int,user:CurrentUser=Depends(get_current_user),svc:MvpService=Depends(service),repo:BigQueryMvpRepository=Depends(repository)):
    identity=svc.identity(user);svc._authorize(identity,clinic_id,"ANAMNESIS_READ");return repo.anamnesis_history(clinic_id,patient_id)


@router.post("/clinicas/{clinic_id}/pacientes/{patient_id}/anamnese/{version_id}/aprovar", tags=["anamnese"])
def approve_anamnesis(clinic_id:int, patient_id:int, version_id:int, payload:ProfessionalApproval, user:CurrentUser=Depends(get_current_user), svc:MvpService=Depends(service), repo:BigQueryMvpRepository=Depends(repository)):
    identity=svc.identity(user)
    svc._authorize(identity,clinic_id,"ANAMNESIS_APPROVE")
    try:
        return repo.approve_anamnesis(clinic_id,patient_id,version_id,payload.model_dump(),identity["id_usuario"])
    except ValueError as exc:
        code=str(exc)
        if code=="ANAMNESIS_VERSION_NOT_FOUND": raise BusinessError(code,"Versão de anamnese não encontrada",404) from exc
        if code=="ANAMNESIS_ALREADY_APPROVED": raise BusinessError(code,"Esta versão já foi aprovada",409) from exc
        raise


@router.post("/clinicas/{clinic_id}/pacientes/{patient_id}/inativar", tags=["pacientes"])
def inactivate(clinic_id:int,patient_id:int,user:CurrentUser=Depends(get_current_user),svc:MvpService=Depends(service),repo:BigQueryMvpRepository=Depends(repository)):
    identity=svc.identity(user);svc._authorize(identity,clinic_id,"PATIENT_WRITE");return repo.set_patient_active(patient_id,False,identity["id_usuario"])


@router.post("/clinicas/{clinic_id}/pacientes/{patient_id}/reativar", tags=["pacientes"])
def reactivate(clinic_id:int,patient_id:int,user:CurrentUser=Depends(get_current_user),svc:MvpService=Depends(service),repo:BigQueryMvpRepository=Depends(repository)):
    identity=svc.identity(user);svc._authorize(identity,clinic_id,"PATIENT_WRITE");return repo.set_patient_active(patient_id,True,identity["id_usuario"])


@router.get("/clinicas/{clinic_id}/anamnese/formulario", tags=["anamnese"])
def current_form(clinic_id: int, user: CurrentUser = Depends(get_current_user), svc: MvpService = Depends(service), repo: BigQueryMvpRepository = Depends(repository)):
    identity = svc.identity(user); svc._authorize(identity, clinic_id, "ANAMNESIS_READ")
    form = repo.get_form(clinic_id)
    if not form:
        raise BusinessError("FORM_NOT_FOUND", "Formulário não encontrado", 404)
    return form


@router.post("/clinicas/{clinic_id}/modo-paciente", status_code=status.HTTP_201_CREATED, tags=["modo-paciente"])
def patient_mode(clinic_id: int, payload: PatientSessionCreate, user: CurrentUser = Depends(get_current_user), svc: MvpService = Depends(service), repo: BigQueryMvpRepository = Depends(repository)):
    identity = svc.identity(user); svc._authorize(identity, clinic_id, "PATIENT_MODE")
    if not repo.has_patient_link(payload.patient_id, clinic_id):
        raise BusinessError("PATIENT_NOT_IN_CLINIC", "Paciente não pertence à clínica", 404)
    if not form_is_available(repo.get_form(clinic_id)):
        raise BusinessError("NO_VALIDATED_FORM", "Não há formulário validado", 409)
    return repo.create_patient_session(clinic_id, payload.patient_id, identity["id_usuario"])


def request_evidence(request: Request) -> tuple[str, str, str]:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    peer = request.client.host if request.client else "unknown"
    ip = f"peer={peer};forwarded={forwarded or 'none'}"
    return ip, request.headers.get("user-agent", "unknown"), request.headers.get("x-request-id") or secrets.token_urlsafe(12)


@router.post("/clinicas/{clinic_id}/anamnese/links", status_code=status.HTTP_201_CREATED, tags=["modo-paciente"])
def create_remote_link(clinic_id:int,payload:RemotePatientSessionCreate,request:Request,user:CurrentUser=Depends(get_current_user),svc:MvpService=Depends(service),repo:BigQueryMvpRepository=Depends(repository)):
    identity=svc.identity(user);svc._authorize(identity,clinic_id,"PATIENT_MODE")
    if not repo.has_patient_link(payload.patient_id,clinic_id): raise BusinessError("PATIENT_NOT_IN_CLINIC","Paciente não pertence à clínica",404)
    if not form_is_available(repo.get_form(clinic_id)): raise BusinessError("NO_VALIDATED_FORM","Não há formulário validado",409)
    try: return repo.create_remote_patient_session(clinic_id,payload.patient_id,identity["id_usuario"],payload.canal_compartilhamento,*request_evidence(request))
    except RuntimeError as exc:
        if str(exc)=="EVIDENCE_HMAC_SECRET_REQUIRED": raise BusinessError("REMOTE_LINK_DISABLED","Chave de evidências não configurada",503) from exc
        raise


@router.get("/clinicas/{clinic_id}/pacientes/{patient_id}/anamnese/links",tags=["modo-paciente"])
def remote_links(clinic_id:int,patient_id:int,user:CurrentUser=Depends(get_current_user),svc:MvpService=Depends(service),repo:BigQueryMvpRepository=Depends(repository)):
    identity=svc.identity(user);svc._authorize(identity,clinic_id,"PATIENT_MODE");return repo.list_remote_sessions(clinic_id,patient_id)


@router.post("/clinicas/{clinic_id}/pacientes/{patient_id}/anamnese/links/{session_id}/revogar",tags=["modo-paciente"])
def revoke_remote_link(clinic_id:int,patient_id:int,session_id:int,user:CurrentUser=Depends(get_current_user),svc:MvpService=Depends(service),repo:BigQueryMvpRepository=Depends(repository)):
    identity=svc.identity(user);svc._authorize(identity,clinic_id,"PATIENT_MODE");return repo.revoke_remote_session(session_id,clinic_id,patient_id,identity["id_usuario"])


def patient_session(x_patient_session: str | None = Header(default=None), repo: BigQueryMvpRepository = Depends(repository)) -> tuple[str, dict]:
    if not x_patient_session or not (session := repo.resolve_patient_session(x_patient_session)):
        raise BusinessError("INVALID_PATIENT_SESSION", "Sessão do paciente inválida ou expirada", 401)
    return x_patient_session, session


def verified_patient_session(context:tuple[str,dict]=Depends(patient_session)):
    session=context[1]
    if session.get("tipo_sessao")=="REMOTE" and not session.get("verified_at"):
        raise BusinessError("IDENTITY_VERIFICATION_REQUIRED","Confirme sua identidade para continuar",403)
    if session.get("bloqueada_em"): raise BusinessError("PATIENT_SESSION_BLOCKED","Este link foi bloqueado",423)
    return context


@router.post("/modo-paciente/verificar",tags=["modo-paciente"])
def verify_remote_identity(payload:RemoteIdentityVerify,request:Request,context:tuple[str,dict]=Depends(patient_session),repo:BigQueryMvpRepository=Depends(repository)):
    token,_=context
    try:return repo.verify_remote_identity(token,payload.cpf,payload.data_nascimento,*request_evidence(request))
    except ValueError as exc:
        code=str(exc)
        if code=="PATIENT_SESSION_BLOCKED": raise BusinessError(code,"Este link foi bloqueado",423) from exc
        if code=="IDENTITY_VERIFICATION_FAILED": raise BusinessError(code,"Não foi possível confirmar os dados informados",401) from exc
        raise BusinessError("INVALID_PATIENT_SESSION","Sessão do paciente inválida ou expirada",401) from exc


@router.get("/modo-paciente/formulario", tags=["modo-paciente"])
def patient_form(context: tuple[str, dict] = Depends(verified_patient_session), repo: BigQueryMvpRepository = Depends(repository)):
    form = repo.get_form_by_id(context[1].get("id_formulario")) if context[1].get("id_formulario") else repo.get_form(context[1]["id_clinica"])
    if not form_is_available(form):
        raise BusinessError("NO_VALIDATED_FORM", "Não há formulário validado", 409)
    return form


@router.post("/modo-paciente/cancelar", tags=["modo-paciente"])
def cancel_patient_mode(context: tuple[str, dict] = Depends(patient_session), repo: BigQueryMvpRepository = Depends(repository)):
    token, _ = context
    repo.revoke_patient_session(token)
    return {"status": "CANCELADA"}


@router.post("/modo-paciente/anamnese", status_code=status.HTTP_201_CREATED, tags=["modo-paciente"])
def submit_patient_anamnesis(payload: AnamnesisSubmit, request:Request, context: tuple[str, dict] = Depends(verified_patient_session), svc: MvpService = Depends(service), repo: BigQueryMvpRepository = Depends(repository)):
    token, session = context
    if session.get("tipo_sessao")=="REMOTE":
        profile=repo.patient_profile(session["id_clinica"],session["id_paciente"]);expected=(profile.get("guardian") or {}).get("cpf") if profile and profile.get("guardian") else profile.get("cpf") if profile else None
        if payload.acceptance.cpf!=expected: raise BusinessError("ACCEPTANCE_IDENTITY_MISMATCH","O CPF do aceite não corresponde à identidade confirmada",422)
    result = svc.submit_anamnesis(None, session["id_clinica"], session["id_paciente"], payload, patient_session=True,form_id=session.get("id_formulario"))
    if session.get("tipo_sessao")=="REMOTE": return repo.finalize_remote_submission(token,session,result,payload.model_dump(mode="json"),*request_evidence(request))
    repo.consume_patient_session(token);return result


@router.get("/clinicas/{clinic_id}/doutores", response_model=PaginatedDoctors, tags=["doutores"])
def list_doctors(clinic_id: int, search: str = Query(default=""), ativo: str = Query(default="all"), page: int = Query(default=1, ge=1), page_size: int = Query(default=25, ge=1, le=100), user: CurrentUser = Depends(get_current_user), svc: MvpService = Depends(service)):
    active: bool | None = None if ativo == "all" else ativo == "true"
    return svc.list_doctors(user, clinic_id, search, active, page, page_size)


@router.get("/clinicas/{clinic_id}/doutores/{doctor_id}", response_model=DoctorDetail, tags=["doutores"])
def get_doctor(clinic_id: int, doctor_id: int, user: CurrentUser = Depends(get_current_user), svc: MvpService = Depends(service)):
    return svc.get_doctor(user, clinic_id, doctor_id)
