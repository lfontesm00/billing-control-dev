import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta

from google.api_core.exceptions import BadRequest
from google.cloud import bigquery

from app.config import settings
from app.core import CurrentUser
from app.utils.identifiers import new_int64_id


class BigQueryMvpRepository:
    """MVP gateway: historical entities live in Trusted; web extensions in bc_* tables."""

    SOURCE = "WEB_APP_V1"

    def __init__(self, client: bigquery.Client | None = None):
        self.client = client or bigquery.Client(project=settings.gcp_project)
        self.dataset = f"{settings.gcp_project}.{settings.bigquery_dataset_trusted}"

    def _bc(self, name: str) -> str:
        return f"`{self.dataset}.bc_{name}`"

    def _trusted(self, name: str) -> str:
        return f"`{self.dataset}.tb_trat_billing_control_{name}`"

    def _table(self, name: str) -> str:  # compatibility for extension callers
        return self._bc(name)

    def _query(self, sql: str, params=None):
        config = bigquery.QueryJobConfig(query_parameters=params or [])
        return self.client.query(sql, job_config=config).result(timeout=30)

    @staticmethod
    def _one(rows):
        for row in rows:
            return dict(row.items())
        return None

    @staticmethod
    def _params(**values):
        return [bigquery.ScalarQueryParameter(name, kind, value) for name, (kind, value) in values.items()]

    def _unique_id(self, table: str, column: str) -> int:
        for _ in range(5):
            candidate = new_int64_id()
            row = self._one(self._query(
                f"SELECT COUNT(*) total FROM {table} WHERE {column}=@id",
                self._params(id=("INT64", candidate)),
            ))
            if not row or not row["total"]:
                return candidate
        raise RuntimeError(f"Falha ao gerar ID único para {column}")

    def resolve_identity(self, user: CurrentUser) -> dict | None:
        result = self._one(self._query(f"""
          WITH target AS (
            SELECT * FROM {self._bc('usuarios')}
            WHERE firebase_uid=@uid OR (firebase_uid IS NULL AND email=@email)
            QUALIFY ROW_NUMBER() OVER(ORDER BY updated_at DESC)=1
          ), profile_codes AS (
            SELECT up.id_usuario,ARRAY_AGG(DISTINCT p.codigo ORDER BY p.codigo) perfis
            FROM {self._bc('usuario_perfis')} up JOIN {self._bc('perfis')} p USING(id_perfil)
            JOIN target t USING(id_usuario) GROUP BY up.id_usuario
          ), permission_codes AS (
            SELECT up.id_usuario,ARRAY_AGG(DISTINCT pm.codigo ORDER BY pm.codigo) permissoes
            FROM {self._bc('usuario_perfis')} up
            JOIN {self._bc('perfil_permissoes')} pp USING(id_perfil)
            JOIN {self._bc('permissoes')} pm USING(id_permissao)
            JOIN target t USING(id_usuario) GROUP BY up.id_usuario
          )
          SELECT t.id_usuario,t.id_organizacao,t.firebase_uid,t.nome,t.email,t.ativo,
            COALESCE(t.troca_senha_obrigatoria,FALSE) troca_senha_obrigatoria,
            IFNULL(pc.perfis,ARRAY<STRING>[]) perfis,
            IFNULL(pm.permissoes,ARRAY<STRING>[]) permissoes
          FROM target t LEFT JOIN profile_codes pc USING(id_usuario) LEFT JOIN permission_codes pm USING(id_usuario)
        """, self._params(uid=("STRING", user.firebase_uid), email=("STRING", user.email))))
        if result and not result.get("firebase_uid"):
            self._query(f"UPDATE {self._bc('usuarios')} SET firebase_uid=@uid,updated_at=CURRENT_TIMESTAMP() WHERE id_usuario=@id", self._params(uid=("STRING", user.firebase_uid), id=("INT64", result["id_usuario"])))
        return result

    def bootstrap(self, user: CurrentUser, organization_name: str) -> dict:
        org = self._unique_id(self._bc("organizacoes"), "id_organizacao")
        uid = self._unique_id(self._bc("usuarios"), "id_usuario")
        up = self._unique_id(self._bc("usuario_perfis"), "id_usuario_perfil")
        self._query(f"""
          BEGIN TRANSACTION;
          ASSERT (SELECT COUNT(*) FROM {self._bc('usuarios')} WHERE firebase_uid=@firebase OR email=@email)=0 AS 'USER_ALREADY_EXISTS';
          INSERT INTO {self._bc('organizacoes')} VALUES (@org,@name,TRUE,CURRENT_TIMESTAMP(),CURRENT_TIMESTAMP());
          INSERT INTO {self._bc('usuarios')} (id_usuario,id_organizacao,firebase_uid,nome,email,ativo,created_at,updated_at)
            VALUES (@user,@org,@firebase,@email,@email,TRUE,CURRENT_TIMESTAMP(),CURRENT_TIMESTAMP());
          INSERT INTO {self._bc('usuario_perfis')} SELECT @up,@user,id_perfil,CURRENT_TIMESTAMP() FROM {self._bc('perfis')} WHERE codigo='FULL_ACCESS';
          COMMIT TRANSACTION;
        """, self._params(org=("INT64", org), user=("INT64", uid), up=("INT64", up), name=("STRING", organization_name), firebase=("STRING", user.firebase_uid), email=("STRING", user.email)))
        return {"id_organizacao": org, "id_usuario": uid, "nome": organization_name}

    def create_invite(self, organization_id: int, data: dict, actor_id: int) -> dict:
        profile = self._one(self._query(f"SELECT id_perfil FROM {self._bc('perfis')} WHERE codigo=@code AND ativo LIMIT 1", self._params(code=("STRING", data["profile_code"]))))
        if not profile:
            raise ValueError("PROFILE_NOT_FOUND")
        user_id = self._unique_id(self._bc("usuarios"), "id_usuario")
        invite_id = self._unique_id(self._bc("convites"), "id_convite")
        profile_link = self._unique_id(self._bc("usuario_perfis"), "id_usuario_perfil")
        expires = datetime.now(UTC) + timedelta(days=7)
        clinic_link_ids = [self._unique_id(self._bc("usuario_clinicas"), "id_usuario_clinica") for _ in data["clinic_ids"]]
        params = self._params(user=("INT64", user_id), org=("INT64", organization_id), email=("STRING", data["email"]), profile_link=("INT64", profile_link), profile=("INT64", profile["id_perfil"]), invite=("INT64", invite_id), expires=("TIMESTAMP", expires), actor=("INT64", actor_id))
        params.append(bigquery.ArrayQueryParameter("clinics", "INT64", data["clinic_ids"]))
        params.append(bigquery.ArrayQueryParameter("clinic_link_ids", "INT64", clinic_link_ids))
        self._query(f"""
          BEGIN TRANSACTION;
          ASSERT (SELECT COUNT(*) FROM {self._bc('usuarios')} WHERE email=@email)=0 AS 'EMAIL_ALREADY_INVITED';
          INSERT INTO {self._bc('usuarios')} (id_usuario,id_organizacao,firebase_uid,nome,email,ativo,created_at,updated_at) VALUES (@user,@org,NULL,@email,@email,TRUE,CURRENT_TIMESTAMP(),CURRENT_TIMESTAMP());
          INSERT INTO {self._bc('usuario_perfis')} VALUES (@profile_link,@user,@profile,CURRENT_TIMESTAMP());
          INSERT INTO {self._bc('usuario_clinicas')}
            SELECT @clinic_link_ids[OFFSET(position)],@user,clinic,TRUE,CURRENT_TIMESTAMP(),CURRENT_TIMESTAMP()
            FROM UNNEST(@clinics) clinic WITH OFFSET position;
          INSERT INTO {self._bc('convites')} VALUES (@invite,@org,@email,@profile,@clinics,'PENDENTE',@expires,@actor,CURRENT_TIMESTAMP());
          COMMIT TRANSACTION;
        """, params)
        return {"id_convite": invite_id, "email": data["email"], "status": "PENDENTE", "expires_at": expires}

    def list_profiles(self):
        return [dict(row.items()) for row in self._query(f"SELECT codigo,nome FROM {self._bc('perfis')} WHERE ativo ORDER BY nome")]

    def list_team_members(self, organization_id: int) -> list[dict]:
        return [dict(row.items()) for row in self._query(f"""
          SELECT u.id_usuario,u.nome,u.email,u.ativo,COALESCE(u.troca_senha_obrigatoria,FALSE) troca_senha_obrigatoria,
            p.codigo profile_code,p.nome perfil_nome,
            ARRAY_AGG(DISTINCT IF(uc.ativo,uc.id_clinica,NULL) IGNORE NULLS) clinic_ids
          FROM {self._bc('usuarios')} u
          JOIN {self._bc('usuario_perfis')} up USING(id_usuario)
          JOIN {self._bc('perfis')} p USING(id_perfil)
          LEFT JOIN {self._bc('usuario_clinicas')} uc USING(id_usuario)
          WHERE u.id_organizacao=@org AND p.codigo IN ('RECEPCAO','FINANCEIRO')
          GROUP BY u.id_usuario,u.nome,u.email,u.ativo,troca_senha_obrigatoria,p.codigo,p.nome
          ORDER BY u.ativo DESC,u.nome
        """, self._params(org=("INT64", organization_id)))]

    def count_active_team_members(self, organization_id: int) -> int:
        row = self._one(self._query(f"""
          SELECT COUNT(DISTINCT u.id_usuario) total FROM {self._bc('usuarios')} u
          JOIN {self._bc('usuario_perfis')} up USING(id_usuario) JOIN {self._bc('perfis')} p USING(id_perfil)
          WHERE u.id_organizacao=@org AND u.ativo AND p.codigo IN ('RECEPCAO','FINANCEIRO')
        """, self._params(org=("INT64", organization_id))))
        return int(row["total"] if row else 0)

    def get_team_member(self, organization_id: int, user_id: int) -> dict | None:
        return self._one(self._query(f"""
          SELECT u.id_usuario,u.firebase_uid,u.nome,u.email,u.ativo,COALESCE(u.troca_senha_obrigatoria,FALSE) troca_senha_obrigatoria,p.codigo profile_code
          FROM {self._bc('usuarios')} u JOIN {self._bc('usuario_perfis')} up USING(id_usuario) JOIN {self._bc('perfis')} p USING(id_perfil)
          WHERE u.id_organizacao=@org AND u.id_usuario=@user AND p.codigo IN ('RECEPCAO','FINANCEIRO') LIMIT 1
        """, self._params(org=("INT64", organization_id), user=("INT64", user_id))))

    def create_team_member(self, organization_id: int, firebase_uid: str, data: dict, actor_id: int) -> dict:
        user_id = self._unique_id(self._bc("usuarios"), "id_usuario")
        profile_link = self._unique_id(self._bc("usuario_perfis"), "id_usuario_perfil")
        audit = self._unique_id(self._bc("auditoria"), "id_auditoria")
        clinic_link_ids = [self._unique_id(self._bc("usuario_clinicas"), "id_usuario_clinica") for _ in data["clinic_ids"]]
        params = self._params(user=("INT64", user_id), org=("INT64", organization_id), firebase=("STRING", firebase_uid), name=("STRING", data["nome"]), email=("STRING", data["email"]), profile_link=("INT64", profile_link), profile=("STRING", data["profile_code"]), actor=("INT64", actor_id), audit=("INT64", audit))
        params.extend([bigquery.ArrayQueryParameter("clinics", "INT64", data["clinic_ids"]), bigquery.ArrayQueryParameter("clinic_link_ids", "INT64", clinic_link_ids)])
        self._query(f"""
          BEGIN TRANSACTION;
          ASSERT (SELECT COUNT(*) FROM {self._bc('usuarios')} WHERE email=@email)=0 AS 'EMAIL_ALREADY_EXISTS';
          ASSERT (SELECT COUNT(DISTINCT u.id_usuario) FROM {self._bc('usuarios')} u JOIN {self._bc('usuario_perfis')} up USING(id_usuario) JOIN {self._bc('perfis')} p USING(id_perfil) WHERE u.id_organizacao=@org AND u.ativo AND p.codigo IN ('RECEPCAO','FINANCEIRO'))<2 AS 'TEAM_MEMBER_LIMIT_REACHED';
          INSERT INTO {self._bc('usuarios')} (id_usuario,id_organizacao,firebase_uid,nome,email,ativo,created_at,updated_at,troca_senha_obrigatoria,alterado_administrativamente_em,alterado_por_id_usuario)
            VALUES(@user,@org,@firebase,@name,@email,TRUE,CURRENT_TIMESTAMP(),CURRENT_TIMESTAMP(),TRUE,CURRENT_TIMESTAMP(),@actor);
          INSERT INTO {self._bc('usuario_perfis')} SELECT @profile_link,@user,id_perfil,CURRENT_TIMESTAMP() FROM {self._bc('perfis')} WHERE codigo=@profile AND ativo;
          INSERT INTO {self._bc('usuario_clinicas')} SELECT @clinic_link_ids[OFFSET(pos)],@user,clinic,TRUE,CURRENT_TIMESTAMP(),CURRENT_TIMESTAMP() FROM UNNEST(@clinics) clinic WITH OFFSET pos;
          INSERT INTO {self._bc('auditoria')} VALUES(@audit,@actor,@org,NULL,'TEAM_MEMBER_CREATED','USUARIO',@user,CURRENT_TIMESTAMP());
          COMMIT TRANSACTION;
        """, params)
        return {"id_usuario": user_id, **data, "ativo": True, "troca_senha_obrigatoria": True}

    def update_team_member(self, organization_id: int, user_id: int, data: dict, actor_id: int) -> dict:
        profile_link = self._unique_id(self._bc("usuario_perfis"), "id_usuario_perfil")
        audit = self._unique_id(self._bc("auditoria"), "id_auditoria")
        clinic_link_ids = [self._unique_id(self._bc("usuario_clinicas"), "id_usuario_clinica") for _ in data["clinic_ids"]]
        params = self._params(user=("INT64", user_id), org=("INT64", organization_id), name=("STRING", data["nome"]), profile=("STRING", data["profile_code"]), profile_link=("INT64", profile_link), actor=("INT64", actor_id), audit=("INT64", audit))
        params.extend([bigquery.ArrayQueryParameter("clinics", "INT64", data["clinic_ids"]), bigquery.ArrayQueryParameter("clinic_link_ids", "INT64", clinic_link_ids)])
        self._query(f"""
          BEGIN TRANSACTION;
          ASSERT (SELECT COUNT(*) FROM {self._bc('usuarios')} u JOIN {self._bc('usuario_perfis')} up USING(id_usuario) JOIN {self._bc('perfis')} p USING(id_perfil) WHERE u.id_usuario=@user AND u.id_organizacao=@org AND p.codigo IN ('RECEPCAO','FINANCEIRO'))=1 AS 'TEAM_MEMBER_NOT_FOUND';
          UPDATE {self._bc('usuarios')} SET nome=@name,updated_at=CURRENT_TIMESTAMP(),alterado_administrativamente_em=CURRENT_TIMESTAMP(),alterado_por_id_usuario=@actor WHERE id_usuario=@user;
          DELETE FROM {self._bc('usuario_perfis')} WHERE id_usuario=@user;
          INSERT INTO {self._bc('usuario_perfis')} SELECT @profile_link,@user,id_perfil,CURRENT_TIMESTAMP() FROM {self._bc('perfis')} WHERE codigo=@profile AND ativo;
          UPDATE {self._bc('usuario_clinicas')} SET ativo=FALSE,updated_at=CURRENT_TIMESTAMP() WHERE id_usuario=@user;
          MERGE {self._bc('usuario_clinicas')} t USING (SELECT @clinic_link_ids[OFFSET(pos)] id_usuario_clinica,clinic id_clinica FROM UNNEST(@clinics) clinic WITH OFFSET pos) s
          ON t.id_usuario=@user AND t.id_clinica=s.id_clinica WHEN MATCHED THEN UPDATE SET ativo=TRUE,updated_at=CURRENT_TIMESTAMP() WHEN NOT MATCHED THEN INSERT VALUES(s.id_usuario_clinica,@user,s.id_clinica,TRUE,CURRENT_TIMESTAMP(),CURRENT_TIMESTAMP());
          INSERT INTO {self._bc('auditoria')} VALUES(@audit,@actor,@org,NULL,'TEAM_MEMBER_UPDATED','USUARIO',@user,CURRENT_TIMESTAMP());
          COMMIT TRANSACTION;
        """, params)
        return {"id_usuario": user_id, **data}

    def set_team_member_active(self, organization_id: int, user_id: int, active: bool, actor_id: int) -> dict:
        action = "TEAM_MEMBER_REACTIVATED" if active else "TEAM_MEMBER_INACTIVATED"
        audit = self._unique_id(self._bc("auditoria"), "id_auditoria")
        self._query(f"""
          BEGIN TRANSACTION;
          ASSERT (SELECT COUNT(*) FROM {self._bc('usuarios')} u JOIN {self._bc('usuario_perfis')} up USING(id_usuario) JOIN {self._bc('perfis')} p USING(id_perfil) WHERE u.id_usuario=@user AND u.id_organizacao=@org AND p.codigo IN ('RECEPCAO','FINANCEIRO'))=1 AS 'TEAM_MEMBER_NOT_FOUND';
          ASSERT NOT @active OR (SELECT COUNT(DISTINCT u.id_usuario) FROM {self._bc('usuarios')} u JOIN {self._bc('usuario_perfis')} up USING(id_usuario) JOIN {self._bc('perfis')} p USING(id_perfil) WHERE u.id_organizacao=@org AND u.ativo AND u.id_usuario!=@user AND p.codigo IN ('RECEPCAO','FINANCEIRO'))<2 AS 'TEAM_MEMBER_LIMIT_REACHED';
          UPDATE {self._bc('usuarios')} SET ativo=@active,updated_at=CURRENT_TIMESTAMP(),alterado_administrativamente_em=CURRENT_TIMESTAMP(),alterado_por_id_usuario=@actor WHERE id_usuario=@user;
          INSERT INTO {self._bc('auditoria')} VALUES(@audit,@actor,@org,NULL,@action,'USUARIO',@user,CURRENT_TIMESTAMP());
          COMMIT TRANSACTION;
        """, self._params(user=("INT64", user_id), org=("INT64", organization_id), active=("BOOL", active), actor=("INT64", actor_id), audit=("INT64", audit), action=("STRING", action)))
        return {"id_usuario": user_id, "ativo": active}

    def mark_temporary_password(self, organization_id: int, user_id: int, actor_id: int) -> None:
        audit = self._unique_id(self._bc("auditoria"), "id_auditoria")
        self._query(f"""
          BEGIN TRANSACTION;
          UPDATE {self._bc('usuarios')} SET troca_senha_obrigatoria=TRUE,updated_at=CURRENT_TIMESTAMP(),alterado_administrativamente_em=CURRENT_TIMESTAMP(),alterado_por_id_usuario=@actor WHERE id_usuario=@user AND id_organizacao=@org;
          INSERT INTO {self._bc('auditoria')} VALUES(@audit,@actor,@org,NULL,'TEAM_MEMBER_PASSWORD_RESET','USUARIO',@user,CURRENT_TIMESTAMP());
          COMMIT TRANSACTION;
        """, self._params(user=("INT64", user_id), org=("INT64", organization_id), actor=("INT64", actor_id), audit=("INT64", audit)))

    def confirm_password_changed(self, user_id: int) -> None:
        self._query(f"UPDATE {self._bc('usuarios')} SET troca_senha_obrigatoria=FALSE,updated_at=CURRENT_TIMESTAMP() WHERE id_usuario=@user AND ativo", self._params(user=("INT64", user_id)))

    def list_clinics(self, firebase_uid: str):
        return [dict(row.items()) for row in self._query(f"""
          WITH latest AS (
            SELECT * FROM {self._trusted('clinicas')}
            QUALIFY ROW_NUMBER() OVER(PARTITION BY id_clinica ORDER BY updated_at DESC,created_at DESC)=1
          )
          SELECT DISTINCT c.id_clinica,c.nome_clinica AS nome,c.razao_social,c.cnpj_cpf,c.email,c.telefone,c.endereco,c.responsavel,c.cro_responsavel,COALESCE(c.status='ATIVO',TRUE) ativo
          FROM latest c
          JOIN {self._bc('organizacao_clinicas')} oc ON oc.id_clinica=c.id_clinica AND oc.ativo
          JOIN {self._bc('usuarios')} u ON u.id_organizacao=oc.id_organizacao
          LEFT JOIN {self._bc('usuario_clinicas')} uc ON uc.id_usuario=u.id_usuario AND uc.id_clinica=c.id_clinica
          WHERE u.firebase_uid=@uid AND u.ativo AND COALESCE(c.status='ATIVO',TRUE)
            AND (uc.ativo OR EXISTS(SELECT 1 FROM {self._bc('usuario_perfis')} up JOIN {self._bc('perfis')} p USING(id_perfil) WHERE up.id_usuario=u.id_usuario AND p.codigo='FULL_ACCESS'))
          ORDER BY nome
        """, self._params(uid=("STRING", firebase_uid)))]

    def count_organization_clinics(self, organization_id: int) -> int:
        row = self._one(self._query(f"SELECT COUNT(DISTINCT id_clinica) total FROM {self._bc('organizacao_clinicas')} WHERE id_organizacao=@org", self._params(org=("INT64", organization_id))))
        return int(row["total"] if row else 0)

    def create_clinic(self, organization_id: int, data: dict, actor_id: int) -> dict:
        clinic = self._unique_id(self._trusted("clinicas"), "id_clinica")
        mapping = self._unique_id(self._bc("organizacao_clinicas"), "id_organizacao_clinica")
        user_mapping = self._unique_id(self._bc("usuario_clinicas"), "id_usuario_clinica")
        audit = self._unique_id(self._bc("auditoria"), "id_auditoria")
        self._query(f"""
          BEGIN TRANSACTION;
          ASSERT (SELECT COUNT(*) FROM {self._trusted('clinicas')} WHERE REGEXP_REPLACE(cnpj_cpf,r'\\D','')=@document)=0 AS 'CLINIC_DOCUMENT_DUPLICATE';
          INSERT INTO {self._trusted('clinicas')} (id_clinica,nome_clinica,razao_social,cnpj_cpf,email,telefone,endereco,responsavel,cro_responsavel,status,origem_registro,created_at,updated_at)
            VALUES (@clinic,@name,@legal_name,@document,@email,@phone,@address,@responsible,@cro,'ATIVO',@source,CURRENT_TIMESTAMP(),CURRENT_TIMESTAMP());
          INSERT INTO {self._bc('organizacao_clinicas')} VALUES (@mapping,@org,@clinic,TRUE,CURRENT_TIMESTAMP(),CURRENT_TIMESTAMP());
          INSERT INTO {self._bc('usuario_clinicas')} (id_usuario_clinica,id_usuario,id_clinica,ativo,created_at,updated_at)
            VALUES (@user_mapping,@actor,@clinic,TRUE,CURRENT_TIMESTAMP(),CURRENT_TIMESTAMP());
          INSERT INTO {self._bc('auditoria')} VALUES (@audit,@actor,@org,@clinic,'CLINIC_CREATED','CLINICA',@clinic,CURRENT_TIMESTAMP());
          COMMIT TRANSACTION;
        """, self._params(clinic=("INT64", clinic), mapping=("INT64", mapping), user_mapping=("INT64", user_mapping), audit=("INT64", audit), actor=("INT64", actor_id), org=("INT64", organization_id), name=("STRING", data["nome"]), legal_name=("STRING", data["razao_social"]), document=("STRING", data["cnpj_cpf"]), email=("STRING", data["email"]), phone=("STRING", data.get("telefone")), address=("STRING", data.get("endereco")), responsible=("STRING", data.get("responsavel")), cro=("STRING", data.get("cro_responsavel")), source=("STRING", self.SOURCE)))
        return {"id_clinica": clinic, **data, "ativo": True}

    def has_permission(self, user_id: int, clinic_id: int | None, permission: str) -> bool:
        row = self._one(self._query(f"""
          SELECT COUNT(*) total FROM {self._bc('usuario_perfis')} up
          JOIN {self._bc('perfil_permissoes')} pp USING(id_perfil) JOIN {self._bc('permissoes')} p USING(id_permissao)
          JOIN {self._bc('usuarios')} u USING(id_usuario)
          LEFT JOIN {self._bc('organizacao_clinicas')} oc ON oc.id_organizacao=u.id_organizacao AND oc.id_clinica=@clinic AND oc.ativo
          LEFT JOIN {self._bc('usuario_clinicas')} uc ON uc.id_usuario=up.id_usuario AND uc.id_clinica=@clinic
          WHERE up.id_usuario=@user AND u.ativo AND p.codigo=@permission
            AND (@clinic IS NULL OR (oc.id_clinica IS NOT NULL AND (uc.ativo OR EXISTS(SELECT 1 FROM {self._bc('perfis')} fp WHERE fp.id_perfil=up.id_perfil AND fp.codigo='FULL_ACCESS'))))
        """, self._params(user=("INT64", user_id), clinic=("INT64", clinic_id), permission=("STRING", permission))))
        return bool(row and row["total"])

    def get_patient_by_cpf(self, cpf: str):
        return self._one(self._query(f"""
          SELECT id_paciente,nome_paciente AS nome,REGEXP_REPLACE(cpf_paciente,r'\\D','') cpf
          FROM {self._trusted('pacientes')} WHERE REGEXP_REPLACE(cpf_paciente,r'\\D','')=@cpf
          QUALIFY ROW_NUMBER() OVER(PARTITION BY id_paciente ORDER BY updated_at DESC,created_at DESC)=1
          ORDER BY updated_at DESC,created_at DESC LIMIT 1
        """, self._params(cpf=("STRING", cpf))))

    def has_patient_link(self, patient_id: int, clinic_id: int) -> bool:
        row = self._one(self._query(f"SELECT COUNT(*) total FROM {self._trusted('paciente_clinica')} WHERE id_paciente=@patient AND id_clinica=@clinic AND COALESCE(flag_paciente_ativo,TRUE)", self._params(patient=("INT64", patient_id), clinic=("INT64", clinic_id))))
        return bool(row and row["total"])

    def get_create_patient_result(self, idempotency_key: str) -> dict | None:
        cached = self._one(self._query(
            f"SELECT result_json FROM {self._bc('idempotencias')} WHERE chave=@key AND operacao='CREATE_PATIENT' LIMIT 1",
            self._params(key=("STRING", idempotency_key)),
        ))
        return json.loads(cached["result_json"]) if cached else None

    def create_patient_with_link(self, clinic_id: int, data: dict, actor_id: int) -> dict:
        cached = self.get_create_patient_result(data["idempotency_key"])
        if cached:
            return cached
        patient = self._unique_id(self._trusted("pacientes"), "id_paciente")
        link = self._unique_id(self._trusted("paciente_clinica"), "id_paciente_clinica")
        guardian_data = data.get("responsavel")
        guardian = self._unique_id(self._bc("responsaveis"), "id_responsavel") if guardian_data else None
        idem = self._unique_id(self._bc("idempotencias"), "id_idempotencia")
        audit = self._unique_id(self._bc("auditoria"), "id_auditoria")
        result = {"id_paciente": patient, "id_clinica": clinic_id}
        try:
            self._query(f"""
              BEGIN TRANSACTION;
              ASSERT (SELECT COUNT(*) FROM {self._trusted('clinicas')} WHERE id_clinica=@clinic)>0 AS 'CLINIC_NOT_FOUND';
              ASSERT (SELECT COUNT(*) FROM {self._trusted('pacientes')} WHERE REGEXP_REPLACE(cpf_paciente,r'\\D','')=@cpf)=0 AS 'PATIENT_DUPLICATE';
              ASSERT (SELECT COUNT(*) FROM {self._bc('idempotencias')} WHERE chave=@key AND operacao='CREATE_PATIENT')=0 AS 'IDEMPOTENCY_CONFLICT';
              INSERT INTO {self._trusted('pacientes')} (id_paciente,fk_anamnese_paciente,nome_paciente,cpf_paciente,dt_nascimento,sexo,telefone,email,endereco,flag_possui_plano_odonto,flag_paciente_ativo,plano_odontologico,origem_registro,created_at,updated_at)
                VALUES (@patient,NULL,@name,@cpf,@birth,@sex,@phone,@email,@address,@has_plan,TRUE,@plan,@source,CURRENT_TIMESTAMP(),CURRENT_TIMESTAMP());
              INSERT INTO {self._trusted('paciente_clinica')} (id_paciente_clinica,id_paciente,id_clinica,data_primeira_consulta,data_ultima_consulta,flag_paciente_ativo,origem_registro,created_at,updated_at)
                VALUES (@link,@patient,@clinic,NULL,NULL,TRUE,@source,CURRENT_TIMESTAMP(),CURRENT_TIMESTAMP());
              IF @guardian IS NOT NULL THEN
                INSERT INTO {self._bc('responsaveis')} (id_responsavel,id_paciente,nome,cpf,telefone,email,parentesco,ativo,created_at,updated_at)
                  VALUES (@guardian,@patient,@gname,@gcpf,@gphone,@gemail,@relation,TRUE,CURRENT_TIMESTAMP(),CURRENT_TIMESTAMP());
              END IF;
              INSERT INTO {self._bc('idempotencias')} VALUES (@idem,@key,'CREATE_PATIENT',@result,CURRENT_TIMESTAMP());
              INSERT INTO {self._bc('auditoria')} VALUES (@audit,@actor,NULL,@clinic,'PATIENT_CREATED','PACIENTE',@patient,CURRENT_TIMESTAMP());
              COMMIT TRANSACTION;
            """, self._params(patient=("INT64", patient), link=("INT64", link), clinic=("INT64", clinic_id), guardian=("INT64", guardian), idem=("INT64", idem), audit=("INT64", audit), actor=("INT64", actor_id), name=("STRING", data["nome"]), cpf=("STRING", data["cpf"]), birth=("DATE", data["data_nascimento"]), sex=("STRING", data["sexo"]), phone=("STRING", data.get("telefone")), email=("STRING", data.get("email")), address=("STRING", data.get("endereco")), has_plan=("BOOL", bool(data.get("plano_odontologico"))), plan=("STRING", data.get("plano_odontologico")), source=("STRING", self.SOURCE), gname=("STRING", guardian_data.get("nome") if guardian_data else None), gcpf=("STRING", guardian_data.get("cpf") if guardian_data else None), gphone=("STRING", guardian_data.get("telefone") if guardian_data else None), gemail=("STRING", guardian_data.get("email") if guardian_data else None), relation=("STRING", guardian_data.get("parentesco") if guardian_data else None), key=("STRING", data["idempotency_key"]), result=("STRING", json.dumps(result))))
        except BadRequest as exc:
            message = str(exc)
            if "PATIENT_DUPLICATE" in message:
                raise ValueError("PATIENT_DUPLICATE") from exc
            if "IDEMPOTENCY_CONFLICT" in message:
                raise ValueError("IDEMPOTENCY_CONFLICT") from exc
            if "CLINIC_NOT_FOUND" in message:
                raise ValueError("CLINIC_NOT_FOUND") from exc
            raise
        return result

    def link_patient(self, patient_id: int, clinic_id: int, actor_id: int) -> dict:
        if self.has_patient_link(patient_id, clinic_id):
            return {"id_paciente": patient_id, "id_clinica": clinic_id, "already_linked": True}
        link = self._unique_id(self._trusted("paciente_clinica"), "id_paciente_clinica")
        audit = self._unique_id(self._bc("auditoria"), "id_auditoria")
        self._query(f"""
          BEGIN TRANSACTION;
          ASSERT (SELECT COUNT(*) FROM {self._trusted('pacientes')} WHERE id_paciente=@patient)>0 AS 'PATIENT_NOT_FOUND';
          ASSERT (SELECT COUNT(*) FROM {self._trusted('clinicas')} WHERE id_clinica=@clinic)>0 AS 'CLINIC_NOT_FOUND';
          INSERT INTO {self._trusted('paciente_clinica')} (id_paciente_clinica,id_paciente,id_clinica,data_primeira_consulta,data_ultima_consulta,flag_paciente_ativo,origem_registro,created_at,updated_at) VALUES (@link,@patient,@clinic,NULL,NULL,TRUE,@source,CURRENT_TIMESTAMP(),CURRENT_TIMESTAMP());
          INSERT INTO {self._bc('auditoria')} VALUES (@audit,@actor,NULL,@clinic,'PATIENT_LINKED','PACIENTE',@patient,CURRENT_TIMESTAMP());
          COMMIT TRANSACTION;
        """, self._params(link=("INT64", link), patient=("INT64", patient_id), clinic=("INT64", clinic_id), source=("STRING", self.SOURCE), audit=("INT64", audit), actor=("INT64", actor_id)))
        return {"id_paciente": patient_id, "id_clinica": clinic_id}

    def list_patients(self, clinic_id: int, search: str, active: bool | None, page: int, page_size: int, anamnesis_status: str | None = None) -> dict:
        active_sql = "" if active is None else "AND COALESCE(p.flag_paciente_ativo,TRUE)=@active AND COALESCE(pc.flag_paciente_ativo,TRUE)=@active"
        params = self._params(clinic=("INT64", clinic_id), search=("STRING", search), digits=("STRING", "".join(filter(str.isdigit, search))), limit=("INT64", page_size), offset=("INT64", (page - 1) * page_size))
        if active is not None:
            params.append(bigquery.ScalarQueryParameter("active", "BOOL", active))
        params.append(bigquery.ScalarQueryParameter("anamnesis_status", "STRING", anamnesis_status))
        result = self._one(self._query(f"""
          WITH patients AS (SELECT * FROM {self._trusted('pacientes')} QUALIFY ROW_NUMBER() OVER(PARTITION BY id_paciente ORDER BY updated_at DESC,created_at DESC)=1),
          links AS (SELECT * FROM {self._trusted('paciente_clinica')} QUALIFY ROW_NUMBER() OVER(PARTITION BY id_paciente,id_clinica ORDER BY updated_at DESC,created_at DESC)=1),
          anamneses AS (SELECT id_clinica,id_paciente,aceito_em,status_aprovacao FROM {self._bc('anamnese_versoes')} QUALIFY ROW_NUMBER() OVER(PARTITION BY id_clinica,id_paciente ORDER BY numero_versao DESC,created_at DESC)=1),
          base AS (
            SELECT p.id_paciente,p.nome_paciente AS nome,REGEXP_REPLACE(p.cpf_paciente,r'\\D','') cpf,p.telefone,COALESCE(p.flag_paciente_ativo,TRUE) ativo,a.aceito_em,
              CASE WHEN a.aceito_em IS NULL THEN 'PENDENTE' WHEN COALESCE(a.status_aprovacao,'PENDENTE_APROVACAO')!='APROVADA' THEN 'PENDENTE_APROVACAO' WHEN TIMESTAMP(DATETIME_ADD(DATETIME(a.aceito_em),INTERVAL 1 YEAR))<=CURRENT_TIMESTAMP() THEN 'VENCIDA' ELSE 'ATUALIZADA' END anamnese_status
            FROM patients p JOIN links pc USING(id_paciente) LEFT JOIN anamneses a ON a.id_clinica=pc.id_clinica AND a.id_paciente=p.id_paciente
            WHERE pc.id_clinica=@clinic {active_sql}
            AND (
              @search=''
              OR CONTAINS_SUBSTR(LOWER(p.nome_paciente),LOWER(@search))
              OR (
                @digits!=''
                AND (
                  REGEXP_REPLACE(p.cpf_paciente,r'\\D','') LIKE CONCAT('%',@digits,'%')
                  OR REGEXP_REPLACE(COALESCE(p.telefone,''),r'\\D','') LIKE CONCAT('%',@digits,'%')
                )
              )
            )
          ), filtered AS (SELECT * FROM base WHERE @anamnesis_status IS NULL OR anamnese_status=@anamnesis_status)
          SELECT
            (SELECT COUNT(*) FROM filtered) total,
            ARRAY(SELECT AS STRUCT id_paciente,nome,cpf,telefone,ativo,aceito_em,anamnese_status FROM filtered ORDER BY nome LIMIT @limit OFFSET @offset) items
        """, params))
        if not result:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}
        rows = [dict(row.items()) if hasattr(row, "items") else dict(row) for row in (result.get("items") or [])]
        return {"items": rows, "total": int(result.get("total") or 0), "page": page, "page_size": page_size}

    def clinic_panel(self, clinic_id: int) -> dict:
        result = self._one(self._query(f"""
          WITH patients AS (SELECT * FROM {self._trusted('pacientes')} QUALIFY ROW_NUMBER() OVER(PARTITION BY id_paciente ORDER BY updated_at DESC,created_at DESC)=1),
          links AS (SELECT * FROM {self._trusted('paciente_clinica')} QUALIFY ROW_NUMBER() OVER(PARTITION BY id_paciente,id_clinica ORDER BY updated_at DESC,created_at DESC)=1),
          anamneses AS (SELECT id_clinica,id_paciente,aceito_em,status_aprovacao FROM {self._bc('anamnese_versoes')} QUALIFY ROW_NUMBER() OVER(PARTITION BY id_clinica,id_paciente ORDER BY numero_versao DESC,created_at DESC)=1),
          base AS (
            SELECT p.id_paciente,p.nome_paciente AS nome,REGEXP_REPLACE(p.cpf_paciente,r'\\D','') cpf,a.aceito_em,
              CASE WHEN a.aceito_em IS NULL THEN 'PENDENTE' WHEN COALESCE(a.status_aprovacao,'PENDENTE_APROVACAO')!='APROVADA' THEN 'PENDENTE_APROVACAO' WHEN TIMESTAMP(DATETIME_ADD(DATETIME(a.aceito_em),INTERVAL 1 YEAR))<=CURRENT_TIMESTAMP() THEN 'VENCIDA' ELSE 'ATUALIZADA' END anamnese_status
            FROM patients p JOIN links pc USING(id_paciente) LEFT JOIN anamneses a ON a.id_clinica=pc.id_clinica AND a.id_paciente=p.id_paciente
            WHERE pc.id_clinica=@clinic AND COALESCE(p.flag_paciente_ativo,TRUE) AND COALESCE(pc.flag_paciente_ativo,TRUE)
          )
          SELECT
            COUNT(*) pacientes_ativos,
            COUNTIF(anamnese_status='PENDENTE') pendentes_preenchimento,
            COUNTIF(anamnese_status='PENDENTE_APROVACAO') pendentes_aprovacao,
            COUNTIF(anamnese_status='ATUALIZADA') atualizadas,
            COUNTIF(anamnese_status='VENCIDA') vencidas,
            ARRAY(SELECT AS STRUCT id_paciente,nome,cpf,aceito_em,anamnese_status FROM base WHERE anamnese_status!='ATUALIZADA' ORDER BY CASE anamnese_status WHEN 'VENCIDA' THEN 1 WHEN 'PENDENTE_APROVACAO' THEN 2 ELSE 3 END,nome LIMIT 5) prioridades
          FROM base
        """, self._params(clinic=("INT64", clinic_id)))) or {}
        result["prioridades"] = [dict(row.items()) if hasattr(row, "items") else dict(row) for row in (result.get("prioridades") or [])]
        return result

    def patient_profile(self, clinic_id: int, patient_id: int):
        patient = self._one(self._query(f"""
          WITH patients AS (SELECT * FROM {self._trusted('pacientes')} QUALIFY ROW_NUMBER() OVER(PARTITION BY id_paciente ORDER BY updated_at DESC,created_at DESC)=1),
          links AS (SELECT * FROM {self._trusted('paciente_clinica')} QUALIFY ROW_NUMBER() OVER(PARTITION BY id_paciente,id_clinica ORDER BY updated_at DESC,created_at DESC)=1)
          SELECT p.id_paciente,p.nome_paciente AS nome,REGEXP_REPLACE(p.cpf_paciente,r'\\D','') cpf,p.dt_nascimento AS data_nascimento,p.sexo,p.telefone,p.email,p.endereco,p.plano_odontologico,COALESCE(p.flag_paciente_ativo,TRUE) ativo
          FROM patients p JOIN links pc USING(id_paciente) WHERE p.id_paciente=@patient AND pc.id_clinica=@clinic LIMIT 1
        """, self._params(patient=("INT64", patient_id), clinic=("INT64", clinic_id))))
        if not patient:
            return None
        patient["guardian"] = self._one(self._query(f"SELECT * EXCEPT(id_paciente) FROM {self._bc('responsaveis')} WHERE id_paciente=@patient AND ativo ORDER BY updated_at DESC LIMIT 1", self._params(patient=("INT64", patient_id))))
        patient["current_anamnesis"] = self._one(self._query(f"""
          SELECT a.* FROM {self._trusted('anamnese_pacientes')} a
          JOIN {self._trusted('pacientes')} p ON p.fk_anamnese_paciente=a.fk_anamnese_paciente OR p.fk_anamnese_paciente=a.id_anamnese OR p.id_paciente=a.id_paciente
          WHERE p.id_paciente=@patient AND a.id_clinica=@clinic
          ORDER BY a.updated_at DESC,a.created_at DESC LIMIT 1
        """, self._params(patient=("INT64", patient_id), clinic=("INT64", clinic_id))))
        patient["latest_anamnesis"] = self._one(self._query(f"SELECT id_anamnese_versao,numero_versao,aceito_em,status_aprovacao FROM {self._bc('anamnese_versoes')} WHERE id_clinica=@clinic AND id_paciente=@patient ORDER BY numero_versao DESC,created_at DESC LIMIT 1", self._params(clinic=("INT64", clinic_id), patient=("INT64", patient_id))))
        patient["alerts"] = [dict(row.items()) for row in self._query(f"SELECT a.codigo,a.descricao FROM {self._bc('alertas_clinicos')} a JOIN {self._bc('anamnese_versoes')} v USING(id_anamnese_versao) WHERE a.id_clinica=@clinic AND a.id_paciente=@patient AND a.ativo AND v.status_aprovacao='APROVADA' ORDER BY a.created_at DESC", self._params(clinic=("INT64", clinic_id), patient=("INT64", patient_id)))]
        return patient

    def anamnesis_history(self, clinic_id: int, patient_id: int):
        return [dict(row.items()) for row in self._query(f"SELECT id_anamnese_versao,numero_versao,aceite_nome,termos_versao,aceito_em,COALESCE(status_aprovacao,'PENDENTE_APROVACAO') status_aprovacao,nome_profissional,cro_profissional,aprovado_em FROM {self._bc('anamnese_versoes')} WHERE id_clinica=@clinic AND id_paciente=@patient ORDER BY numero_versao DESC", self._params(clinic=("INT64", clinic_id), patient=("INT64", patient_id)))]

    def set_patient_active(self, patient_id: int, active: bool, actor_id: int) -> dict:
        audit = self._unique_id(self._bc("auditoria"), "id_auditoria")
        self._query(f"""
          BEGIN TRANSACTION;
          UPDATE {self._trusted('pacientes')} p SET flag_paciente_ativo=@active,updated_at=CURRENT_TIMESTAMP()
          WHERE id_paciente=@patient AND COALESCE(updated_at,created_at,TIMESTAMP '1970-01-01')=(SELECT MAX(COALESCE(x.updated_at,x.created_at,TIMESTAMP '1970-01-01')) FROM {self._trusted('pacientes')} x WHERE x.id_paciente=p.id_paciente);
          UPDATE {self._trusted('paciente_clinica')} pc SET flag_paciente_ativo=@active,updated_at=CURRENT_TIMESTAMP()
          WHERE id_paciente=@patient AND COALESCE(updated_at,created_at,TIMESTAMP '1970-01-01')=(SELECT MAX(COALESCE(x.updated_at,x.created_at,TIMESTAMP '1970-01-01')) FROM {self._trusted('paciente_clinica')} x WHERE x.id_paciente=pc.id_paciente AND x.id_clinica=pc.id_clinica);
          INSERT INTO {self._bc('auditoria')} VALUES (@audit,@actor,NULL,NULL,@action,'PACIENTE',@patient,CURRENT_TIMESTAMP());
          COMMIT TRANSACTION;
        """, self._params(active=("BOOL", active), patient=("INT64", patient_id), audit=("INT64", audit), actor=("INT64", actor_id), action=("STRING", "PATIENT_REACTIVATED" if active else "PATIENT_INACTIVATED")))
        return {"id_paciente": patient_id, "ativo": active}

    def get_form(self, clinic_id: int):
        form = self._one(self._query(f"""
          SELECT * FROM {self._bc('formularios')}
          WHERE (id_clinica=@clinic OR id_clinica IS NULL)
            AND (status='PUBLICADO' OR (@allow_test AND status='PUBLICADO_TESTE'))
          ORDER BY id_clinica DESC,versao DESC LIMIT 1
        """, self._params(clinic=("INT64", clinic_id), allow_test=("BOOL", settings.allow_unvalidated_test_forms))))
        if not form:
            return None
        form["questions"] = [dict(row.items()) for row in self._query(f"SELECT * FROM {self._bc('perguntas')} WHERE id_formulario=@form ORDER BY ordem", self._params(form=("INT64", form["id_formulario"])))]
        form["modo_teste"] = form.get("status") == "PUBLICADO_TESTE"
        form["uso_clinico"] = form.get("status") == "PUBLICADO" and bool(form.get("validado_clinicamente"))
        return form

    def get_form_by_id(self, form_id: int):
        form = self._one(self._query(f"SELECT * FROM {self._bc('formularios')} WHERE id_formulario=@form LIMIT 1", self._params(form=("INT64", form_id))))
        if not form:
            return None
        form["questions"] = [dict(row.items()) for row in self._query(f"SELECT * FROM {self._bc('perguntas')} WHERE id_formulario=@form ORDER BY ordem", self._params(form=("INT64", form_id)))]
        form["modo_teste"] = form.get("status") == "PUBLICADO_TESTE"
        form["uso_clinico"] = form.get("status") == "PUBLICADO" and bool(form.get("validado_clinicamente"))
        return form

    def submit_anamnesis(self, clinic_id: int, patient_id: int, data: dict, actor_id: int | None) -> dict:
        cached = self._one(self._query(f"SELECT result_json FROM {self._bc('idempotencias')} WHERE chave=@key AND operacao='SUBMIT_ANAMNESIS' LIMIT 1", self._params(key=("STRING", data["idempotency_key"]))))
        if cached:
            return json.loads(cached["result_json"])
        version = self._unique_id(self._bc("anamnese_versoes"), "id_anamnese_versao")
        current = self._one(self._query(f"SELECT fk_anamnese_paciente FROM {self._trusted('pacientes')} WHERE id_paciente=@patient ORDER BY updated_at DESC,created_at DESC LIMIT 1", self._params(patient=("INT64", patient_id))))
        anamnesis = current.get("fk_anamnese_paciente") if current else None
        if anamnesis is None:
            anamnesis = self._unique_id(self._trusted("anamnese_pacientes"), "id_anamnese")
        idem = self._unique_id(self._bc("idempotencias"), "id_idempotencia")
        audit = self._unique_id(self._bc("auditoria"), "id_auditoria")
        form = self.get_form(clinic_id) or {"questions": []}
        answer_map = {a["question_id"]: a.get("value") for a in data["answers"]}
        alerts = [{"id": new_int64_id(), "code": q["alert_code"], "description": q.get("alert_template") or q["alert_code"]} for q in form["questions"] if q.get("alert_code") and answer_map.get(q["id_pergunta"]) is True]
        hypertension_question = next((q["id_pergunta"] for q in form["questions"] if q.get("codigo") == "HIPERTENSAO"), None)
        hypertension = answer_map.get(hypertension_question)
        allergy_question = next((q["id_pergunta"] for q in form["questions"] if q.get("codigo") == "ALERGIA"), None)
        allergy = answer_map.get(allergy_question)
        def answer_for(code):
            question_id = next((q["id_pergunta"] for q in form["questions"] if q.get("codigo") == code), None)
            return answer_map.get(question_id)
        historical_flags = {
            "surgery": answer_for("CIRURGIA"), "medical": answer_for("TRATAMENTO_MEDICO"),
            "medicine": answer_for("MEDICAMENTO_CONTINUO"), "healing": answer_for("DIFICULDADE_CICATRIZACAO"),
            "bleeding": answer_for("SANGRAMENTO_EXAGERADO"), "pregnant": answer_for("GESTANTE"),
            "liver": answer_for("PROBLEMA_FIGADO"), "diabetes": answer_for("DIABETES"),
            "cardiac": answer_for("PROBLEMA_CARDIACO"), "renal": answer_for("PROBLEMA_RENAL"),
            "asthma": answer_for("ASMATICO"), "smoker": answer_for("FUMANTE"),
            "vape": answer_for("CIGARRO_ELETRONICO"), "dizziness": answer_for("TONTURAS"),
            "family": answer_for("DOENCA_FAMILIA"), "comments": answer_for("COMENTARIOS"),
        }
        self._query(f"""
          DECLARE next_version INT64 DEFAULT (SELECT COALESCE(MAX(numero_versao),0)+1 FROM {self._bc('anamnese_versoes')} WHERE id_clinica=@clinic AND id_paciente=@patient);
          BEGIN TRANSACTION;
          ASSERT (SELECT COUNT(*) FROM {self._trusted('paciente_clinica')} WHERE id_paciente=@patient AND id_clinica=@clinic AND COALESCE(flag_paciente_ativo,TRUE))>0 AS 'PATIENT_NOT_IN_CLINIC';
          ASSERT (SELECT COUNT(*) FROM {self._bc('idempotencias')} WHERE chave=@key AND operacao='SUBMIT_ANAMNESIS')=0 AS 'IDEMPOTENCY_CONFLICT';
          INSERT INTO {self._bc('anamnese_versoes')} (id_anamnese_versao,id_formulario,id_clinica,id_paciente,numero_versao,id_usuario_responsavel,aceite_nome,aceite_cpf,termos_aceitos,termos_versao,respostas_json,aceito_em,created_at,status_aprovacao)
            VALUES (@version,@form,@clinic,@patient,next_version,@actor,@acceptance_name,@acceptance_cpf,TRUE,@terms,@answers,CURRENT_TIMESTAMP(),CURRENT_TIMESTAMP(),'PENDENTE_APROVACAO');
          MERGE {self._trusted('anamnese_pacientes')} target USING (SELECT @anamnesis id_anamnese,@patient id_paciente,@clinic id_clinica) source
          ON target.fk_anamnese_paciente=source.id_anamnese AND target.id_clinica=source.id_clinica
          WHEN MATCHED THEN UPDATE SET id_formulario=@form,respostas_json=@answers,flag_ja_fez_alguma_cirurgia=COALESCE(@surgery,target.flag_ja_fez_alguma_cirurgia),flag_ja_fez_tratamento_medico=COALESCE(@medical,target.flag_ja_fez_tratamento_medico),flag_uso_continuo_medicamento=COALESCE(@medicine,target.flag_uso_continuo_medicamento),flag_alergia_medicamento=COALESCE(@allergy,target.flag_alergia_medicamento),flag_dificuldade_cicatrizacao=COALESCE(@healing,target.flag_dificuldade_cicatrizacao),flag_sangramento_exagerado=COALESCE(@bleeding,target.flag_sangramento_exagerado),flag_gestante=COALESCE(@pregnant,target.flag_gestante),flag_problema_figado_ou_rim=COALESCE(@liver,target.flag_problema_figado_ou_rim),flag_diabetes=COALESCE(@diabetes,target.flag_diabetes),flag_hipertenso=COALESCE(@hypertension,target.flag_hipertenso),flag_problema_cardiaco=COALESCE(@cardiac,target.flag_problema_cardiaco),flag_problema_renal=COALESCE(@renal,target.flag_problema_renal),flag_asmatico=COALESCE(@asthma,target.flag_asmatico),flag_fumante=COALESCE(@smoker,target.flag_fumante),flag_uso_cigarro_eletronico=COALESCE(@vape,target.flag_uso_cigarro_eletronico),flag_costuma_sentir_tonturas=COALESCE(@dizziness,target.flag_costuma_sentir_tonturas),flag_doenca_na_familia=COALESCE(@family,target.flag_doenca_na_familia),comentarios=COALESCE(@comments,target.comentarios),aceite_nome=@acceptance_name,aceite_cpf=@acceptance_cpf,termos_versao=@terms,aceito_em=CURRENT_TIMESTAMP(),origem_registro=@source,updated_at=CURRENT_TIMESTAMP()
          WHEN NOT MATCHED THEN INSERT (id_anamnese,fk_anamnese_paciente,id_paciente,id_clinica,id_formulario,respostas_json,flag_ja_fez_alguma_cirurgia,flag_ja_fez_tratamento_medico,flag_uso_continuo_medicamento,flag_alergia_medicamento,flag_dificuldade_cicatrizacao,flag_sangramento_exagerado,flag_gestante,flag_problema_figado_ou_rim,flag_diabetes,flag_hipertenso,flag_problema_cardiaco,flag_problema_renal,flag_asmatico,flag_fumante,flag_uso_cigarro_eletronico,flag_costuma_sentir_tonturas,flag_doenca_na_familia,comentarios,aceite_nome,aceite_cpf,termos_versao,aceito_em,origem_registro,created_at,updated_at)
            VALUES (@anamnesis,@anamnesis,@patient,@clinic,@form,@answers,@surgery,@medical,@medicine,@allergy,@healing,@bleeding,@pregnant,@liver,@diabetes,@hypertension,@cardiac,@renal,@asthma,@smoker,@vape,@dizziness,@family,@comments,@acceptance_name,@acceptance_cpf,@terms,CURRENT_TIMESTAMP(),@source,CURRENT_TIMESTAMP(),CURRENT_TIMESTAMP());
          UPDATE {self._trusted('pacientes')} p SET fk_anamnese_paciente=@anamnesis,updated_at=CURRENT_TIMESTAMP()
          WHERE id_paciente=@patient AND COALESCE(updated_at,created_at,TIMESTAMP '1970-01-01')=(SELECT MAX(COALESCE(x.updated_at,x.created_at,TIMESTAMP '1970-01-01')) FROM {self._trusted('pacientes')} x WHERE x.id_paciente=p.id_paciente);
          UPDATE {self._bc('alertas_clinicos')} SET ativo=FALSE WHERE id_clinica=@clinic AND id_paciente=@patient AND ativo;
          INSERT INTO {self._bc('alertas_clinicos')} SELECT CAST(JSON_VALUE(item,'$.id') AS INT64),@version,@clinic,@patient,JSON_VALUE(item,'$.code'),JSON_VALUE(item,'$.description'),TRUE,CURRENT_TIMESTAMP() FROM UNNEST(JSON_QUERY_ARRAY(@alerts)) item;
          INSERT INTO {self._bc('idempotencias')} VALUES (@idem,@key,'SUBMIT_ANAMNESIS',TO_JSON_STRING(STRUCT(@version AS id_anamnese_versao,next_version AS numero_versao,'PENDENTE_APROVACAO' AS status)),CURRENT_TIMESTAMP());
          INSERT INTO {self._bc('auditoria')} VALUES (@audit,@actor,NULL,@clinic,'ANAMNESIS_SUBMITTED','ANAMNESE',@version,CURRENT_TIMESTAMP());
          COMMIT TRANSACTION;
        """, self._params(version=("INT64", version), anamnesis=("INT64", anamnesis), form=("INT64", data["form_id"]), clinic=("INT64", clinic_id), patient=("INT64", patient_id), actor=("INT64", actor_id), acceptance_name=("STRING", data["acceptance"]["nome"]), acceptance_cpf=("STRING", data["acceptance"]["cpf"]), terms=("STRING", data["terms_version"]), answers=("JSON", data["answers"]), allergy=("BOOL", allergy), hypertension=("BOOL", hypertension), source=("STRING", self.SOURCE), alerts=("JSON", alerts), idem=("INT64", idem), key=("STRING", data["idempotency_key"]), audit=("INT64", audit), **{key:(("STRING" if key=="comments" else "BOOL"),value) for key,value in historical_flags.items()}))
        stored = self._one(self._query(f"SELECT result_json FROM {self._bc('idempotencias')} WHERE chave=@key AND operacao='SUBMIT_ANAMNESIS' LIMIT 1", self._params(key=("STRING", data["idempotency_key"]))))
        return json.loads(stored["result_json"]) if stored else {"id_anamnese_versao": version, "status": "PENDENTE_APROVACAO"}

    def approve_anamnesis(self, clinic_id: int, patient_id: int, version_id: int, data: dict, actor_id: int) -> dict:
        version = self._one(self._query(f"SELECT id_anamnese_versao,status_aprovacao FROM {self._bc('anamnese_versoes')} WHERE id_anamnese_versao=@version AND id_clinica=@clinic AND id_paciente=@patient LIMIT 1", self._params(version=("INT64",version_id),clinic=("INT64",clinic_id),patient=("INT64",patient_id))))
        if not version:
            raise ValueError("ANAMNESIS_VERSION_NOT_FOUND")
        if version.get("status_aprovacao") == "APROVADA":
            raise ValueError("ANAMNESIS_ALREADY_APPROVED")
        audit = self._unique_id(self._bc("auditoria"), "id_auditoria")
        self._query(f"""
          BEGIN TRANSACTION;
          UPDATE {self._bc('anamnese_versoes')}
          SET status_aprovacao='APROVADA',id_profissional_aprovador=@actor,nome_profissional=@name,cro_profissional=@cro,aprovado_em=CURRENT_TIMESTAMP()
          WHERE id_anamnese_versao=@version AND id_clinica=@clinic AND id_paciente=@patient AND COALESCE(status_aprovacao,'PENDENTE_APROVACAO')!='APROVADA';
          INSERT INTO {self._bc('auditoria')} VALUES (@audit,@actor,NULL,@clinic,'ANAMNESIS_APPROVED','ANAMNESE',@version,CURRENT_TIMESTAMP());
          COMMIT TRANSACTION;
        """, self._params(version=("INT64",version_id),clinic=("INT64",clinic_id),patient=("INT64",patient_id),actor=("INT64",actor_id),name=("STRING",data["nome_profissional"]),cro=("STRING",data["cro_profissional"]),audit=("INT64",audit)))
        return {"id_anamnese_versao":version_id,"status":"APROVADA"}

    def create_patient_session(self, clinic_id: int, patient_id: int, actor_id: int) -> dict:
        raw = secrets.token_urlsafe(32)
        digest = hashlib.sha256(raw.encode()).hexdigest()
        created = datetime.now(UTC)
        expires = created + timedelta(minutes=settings.patient_session_minutes)
        session = self._unique_id(self._bc("sessoes_paciente"), "id_sessao")
        form = self.get_form(clinic_id)
        self._query(f"""INSERT INTO {self._bc('sessoes_paciente')}
          (id_sessao,token_hash,id_clinica,id_paciente,id_usuario_criador,expires_at,revogada_em,usada,created_at,tipo_sessao,id_formulario,versao_formulario,tentativas_verificacao)
          VALUES (@id,@hash,@clinic,@patient,@actor,@expires,NULL,FALSE,@created,'LOCAL',@form,@form_version,0)""", self._params(id=("INT64", session), hash=("STRING", digest), clinic=("INT64", clinic_id), patient=("INT64", patient_id), actor=("INT64", actor_id), expires=("TIMESTAMP", expires), created=("TIMESTAMP", created), form=("INT64", form["id_formulario"] if form else None), form_version=("INT64", form["versao"] if form else None)))
        return {"token": raw, "expires_at": expires}

    def _evidence_digest(self, value: str) -> str:
        if not settings.evidence_hmac_secret:
            raise RuntimeError("EVIDENCE_HMAC_SECRET_REQUIRED")
        return hmac.new(settings.evidence_hmac_secret.encode(), value.encode(), hashlib.sha256).hexdigest()

    def record_session_evidence(self, session: dict, event: str, ip: str, user_agent: str, request_id: str, content_hash: str | None = None):
        evidence_id = self._unique_id(self._bc("anamnesis_evidence"), "id_evidencia")
        self._query(f"""INSERT INTO {self._bc('anamnesis_evidence')}
          (id_evidencia,id_sessao,id_clinica,id_paciente,id_formulario,event_type,request_id,ip_hmac,user_agent,user_agent_hash,content_hmac,key_version,origem_registro,created_at)
          VALUES (@id,@session,@clinic,@patient,@form,@event,@request,@ip,@ua,@uah,@content,@key,@source,CURRENT_TIMESTAMP())""",
          self._params(id=("INT64",evidence_id),session=("INT64",session["id_sessao"]),clinic=("INT64",session["id_clinica"]),patient=("INT64",session["id_paciente"]),form=("INT64",session.get("id_formulario")),event=("STRING",event),request=("STRING",request_id),ip=("STRING",self._evidence_digest(ip or "unknown")),ua=("STRING",(user_agent or "")[:500]),uah=("STRING",self._evidence_digest(user_agent or "unknown")),content=("STRING",content_hash),key=("STRING",settings.evidence_hmac_key_version),source=("STRING",self.SOURCE)))
        return evidence_id

    def create_remote_patient_session(self, clinic_id: int, patient_id: int, actor_id: int, channel: str, ip: str, user_agent: str, request_id: str) -> dict:
        if not settings.evidence_hmac_secret:
            raise RuntimeError("EVIDENCE_HMAC_SECRET_REQUIRED")
        form = self.get_form(clinic_id)
        raw = secrets.token_urlsafe(32); digest = hashlib.sha256(raw.encode()).hexdigest()
        created = datetime.now(UTC); expires = created + timedelta(hours=settings.remote_patient_session_hours)
        session_id = self._unique_id(self._bc("sessoes_paciente"), "id_sessao")
        audit = self._unique_id(self._bc("auditoria"), "id_auditoria")
        self._query(f"""BEGIN TRANSACTION;
          UPDATE {self._bc('sessoes_paciente')} SET revogada_em=CURRENT_TIMESTAMP()
            WHERE id_clinica=@clinic AND id_paciente=@patient AND tipo_sessao='REMOTE' AND NOT usada AND revogada_em IS NULL AND expires_at>CURRENT_TIMESTAMP();
          INSERT INTO {self._bc('sessoes_paciente')}
            (id_sessao,token_hash,id_clinica,id_paciente,id_usuario_criador,expires_at,revogada_em,usada,created_at,tipo_sessao,id_formulario,versao_formulario,tentativas_verificacao,canal_compartilhamento,key_version)
            VALUES (@id,@hash,@clinic,@patient,@actor,@expires,NULL,FALSE,@created,'REMOTE',@form,@form_version,0,@channel,@key);
          INSERT INTO {self._bc('auditoria')} VALUES (@audit,@actor,NULL,@clinic,'ANAMNESIS_LINK_CREATED','SESSAO_PACIENTE',@id,CURRENT_TIMESTAMP());
          COMMIT TRANSACTION;""", self._params(id=("INT64",session_id),hash=("STRING",digest),clinic=("INT64",clinic_id),patient=("INT64",patient_id),actor=("INT64",actor_id),expires=("TIMESTAMP",expires),created=("TIMESTAMP",created),form=("INT64",form["id_formulario"]),form_version=("INT64",form["versao"]),channel=("STRING",channel),key=("STRING",settings.evidence_hmac_key_version),audit=("INT64",audit)))
        session={"id_sessao":session_id,"id_clinica":clinic_id,"id_paciente":patient_id,"id_formulario":form["id_formulario"]}
        self.record_session_evidence(session,"LINK_CREATED",ip,user_agent,request_id)
        return {"token":raw,"expires_at":expires,"url":f"{settings.public_site_url.rstrip('/')}/anamnese/responder#token={raw}"}

    def verify_remote_identity(self, raw: str, cpf: str, birth_date, ip: str, user_agent: str, request_id: str) -> dict:
        session = self.resolve_patient_session(raw)
        if not session or session.get("tipo_sessao") != "REMOTE": raise ValueError("INVALID_PATIENT_SESSION")
        if session.get("bloqueada_em"): raise ValueError("PATIENT_SESSION_BLOCKED")
        profile = self.patient_profile(session["id_clinica"],session["id_paciente"])
        expected = (profile.get("guardian") or {}).get("cpf") if profile and profile.get("guardian") else profile.get("cpf") if profile else None
        role = "RESPONSAVEL" if profile and profile.get("guardian") else "PACIENTE"
        valid = bool(profile and expected == cpf and str(profile.get("data_nascimento")) == str(birth_date))
        audit = self._unique_id(self._bc("auditoria"), "id_auditoria") if valid else None
        self._query(f"""UPDATE {self._bc('sessoes_paciente')}
          SET tentativas_verificacao=tentativas_verificacao+1,
              verified_at=IF(@valid,CURRENT_TIMESTAMP(),verified_at),papel_confirmante=IF(@valid,@role,papel_confirmante),
              bloqueada_em=IF(NOT @valid AND tentativas_verificacao+1>=@max,CURRENT_TIMESTAMP(),bloqueada_em)
          WHERE id_sessao=@id;
          IF @valid THEN INSERT INTO {self._bc('auditoria')} VALUES (@audit,NULL,NULL,@clinic,'ANAMNESIS_IDENTITY_VERIFIED','SESSAO_PACIENTE',@id,CURRENT_TIMESTAMP()); END IF;""", self._params(valid=("BOOL",valid),role=("STRING",role),max=("INT64",settings.remote_patient_max_attempts),id=("INT64",session["id_sessao"]),audit=("INT64",audit),clinic=("INT64",session["id_clinica"])))
        if not valid: raise ValueError("IDENTITY_VERIFICATION_FAILED")
        session["papel_confirmante"]=role
        self.record_session_evidence(session,"IDENTITY_VERIFIED",ip,user_agent,request_id)
        return {"verified":True,"papel_confirmante":role}

    def list_remote_sessions(self, clinic_id: int, patient_id: int):
        return [dict(r.items()) for r in self._query(f"SELECT id_sessao,canal_compartilhamento,created_at,expires_at,verified_at,revogada_em,usada,bloqueada_em FROM {self._bc('sessoes_paciente')} WHERE id_clinica=@clinic AND id_paciente=@patient AND tipo_sessao='REMOTE' ORDER BY created_at DESC LIMIT 20", self._params(clinic=("INT64",clinic_id),patient=("INT64",patient_id)))]

    def revoke_remote_session(self, session_id: int, clinic_id: int, patient_id: int, actor_id: int):
        audit=self._unique_id(self._bc("auditoria"),"id_auditoria")
        self._query(f"""BEGIN TRANSACTION; UPDATE {self._bc('sessoes_paciente')} SET revogada_em=CURRENT_TIMESTAMP() WHERE id_sessao=@id AND id_clinica=@clinic AND id_paciente=@patient AND tipo_sessao='REMOTE' AND NOT usada AND revogada_em IS NULL; INSERT INTO {self._bc('auditoria')} VALUES(@audit,@actor,NULL,@clinic,'ANAMNESIS_LINK_REVOKED','SESSAO_PACIENTE',@id,CURRENT_TIMESTAMP()); COMMIT TRANSACTION;""",self._params(id=("INT64",session_id),clinic=("INT64",clinic_id),patient=("INT64",patient_id),audit=("INT64",audit),actor=("INT64",actor_id)))
        return {"id_sessao":session_id,"status":"REVOGADA"}

    def finalize_remote_submission(self, raw: str, session: dict, result: dict, payload: dict, ip: str, user_agent: str, request_id: str):
        form = self.get_form_by_id(session["id_formulario"]) or {}
        canonical = json.dumps({"session_id":session["id_sessao"],"clinic_id":session["id_clinica"],"patient_id":session["id_paciente"],"form_id":session["id_formulario"],"form_version":session.get("versao_formulario"),"terms_version":form.get("termos_versao"),"terms_text":form.get("termos_texto"),"questions":[{"id":q.get("id_pergunta"),"code":q.get("codigo"),"text":q.get("texto"),"type":q.get("tipo"),"required":q.get("obrigatoria")} for q in form.get("questions",[])],"answers":payload["answers"],"acceptance":payload["acceptance"],"anamnesis_version_id":result.get("id_anamnese_versao"),"version_number":result.get("numero_versao"),"request_id":request_id},ensure_ascii=False,sort_keys=True,separators=(",",":"))
        content_hmac=self._evidence_digest(canonical)
        evidence_id=self.record_session_evidence(session,"REMOTE_SUBMITTED",ip,user_agent,request_id,content_hmac)
        audit=self._unique_id(self._bc("auditoria"),"id_auditoria")
        self._query(f"""BEGIN TRANSACTION;
          UPDATE {self._bc('anamnese_versoes')} SET id_sessao_origem=@session,id_evidencia=@evidence,content_hmac=@content,key_version=@key,papel_confirmante=@role
            WHERE id_anamnese_versao=@version;
          UPDATE {self._bc('sessoes_paciente')} SET usada=TRUE WHERE id_sessao=@session AND NOT usada;
          INSERT INTO {self._bc('auditoria')} VALUES(@audit,NULL,NULL,@clinic,'ANAMNESIS_REMOTE_SUBMITTED','ANAMNESE',@version,CURRENT_TIMESTAMP());
          COMMIT TRANSACTION;""",self._params(session=("INT64",session["id_sessao"]),evidence=("INT64",evidence_id),content=("STRING",content_hmac),key=("STRING",settings.evidence_hmac_key_version),role=("STRING",session.get("papel_confirmante")),version=("INT64",result["id_anamnese_versao"]),audit=("INT64",audit),clinic=("INT64",session["id_clinica"])))
        return result | {"evidence_id":evidence_id}

    def resolve_patient_session(self, raw: str):
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return self._one(self._query(f"SELECT * FROM {self._bc('sessoes_paciente')} WHERE token_hash=@hash AND NOT usada AND revogada_em IS NULL AND expires_at>CURRENT_TIMESTAMP() LIMIT 1", self._params(hash=("STRING", digest))))

    def consume_patient_session(self, raw: str):
        digest = hashlib.sha256(raw.encode()).hexdigest()
        self._query(f"UPDATE {self._bc('sessoes_paciente')} SET usada=TRUE WHERE token_hash=@hash", self._params(hash=("STRING", digest)))

    def revoke_patient_session(self, raw: str):
        digest = hashlib.sha256(raw.encode()).hexdigest()
        self._query(f"UPDATE {self._bc('sessoes_paciente')} SET revogada_em=CURRENT_TIMESTAMP() WHERE token_hash=@hash AND NOT usada AND revogada_em IS NULL", self._params(hash=("STRING", digest)))

    def get_financial_summary(self, clinic_id: int, mes_ano: str | None = None) -> dict:
        params = self._params(clinic=("INT64", clinic_id))
        periodo_consultas = "AND mes_consulta = @mes_ano" if mes_ano else ""
        periodo_despesas = "AND mes_ano = @mes_ano" if mes_ano else ""
        if mes_ano:
            params.append(bigquery.ScalarQueryParameter("mes_ano", "STRING", mes_ano))
        result = self._one(self._query(f"""
          WITH consultas AS (
            SELECT COALESCE(valor_total, 0) valor_total
            FROM {self._trusted('consultas')}
            WHERE id_clinica = @clinic AND status = 'FINALIZADA'
            {periodo_consultas}
            QUALIFY ROW_NUMBER() OVER(PARTITION BY id_consulta ORDER BY updated_at DESC, created_at DESC) = 1
          ),
          despesas AS (
            SELECT COALESCE(valor_despesa, 0) valor_despesa
            FROM {self._trusted('despesas')}
            WHERE id_clinica = @clinic
            {periodo_despesas}
            QUALIFY ROW_NUMBER() OVER(PARTITION BY id_despesa ORDER BY updated_at DESC, created_at DESC) = 1
          )
          SELECT
            COALESCE(SUM(c.valor_total), 0) producao_estimada,
            COUNT(c.valor_total) total_consultas,
            COALESCE((SELECT SUM(d.valor_despesa) FROM despesas d), 0) total_despesas,
            COALESCE((SELECT COUNT(*) FROM despesas), 0) total_despesas_count
          FROM consultas c
        """, params))
        if not result:
            return {"producao_estimada": 0.0, "total_despesas": 0.0, "resultado_estimado": 0.0, "total_consultas": 0, "total_despesas_count": 0}
        producao = float(result.get("producao_estimada") or 0)
        despesas = float(result.get("total_despesas") or 0)
        return {
            "producao_estimada": producao,
            "total_despesas": despesas,
            "resultado_estimado": producao - despesas,
            "total_consultas": int(result.get("total_consultas") or 0),
            "total_despesas_count": int(result.get("total_despesas_count") or 0),
        }

    def list_expenses(self, clinic_id: int, mes_ano: str | None = None, page: int = 1, page_size: int = 25) -> dict:
        params = self._params(clinic=("INT64", clinic_id), limit=("INT64", page_size), offset=("INT64", (page - 1) * page_size))
        periodo = "AND mes_ano = @mes_ano" if mes_ano else ""
        if mes_ano:
            params.append(bigquery.ScalarQueryParameter("mes_ano", "STRING", mes_ano))
        result = self._one(self._query(f"""
          WITH base AS (
            SELECT id_despesa, id_clinica, nome_despesa, prestador,
              data_vencimento, CAST(mes_ano AS STRING) mes_ano,
              status, valor_despesa, data_pagamento
            FROM {self._trusted('despesas')}
            WHERE id_clinica = @clinic
            {periodo}
            QUALIFY ROW_NUMBER() OVER(PARTITION BY id_despesa ORDER BY updated_at DESC, created_at DESC) = 1
          )
          SELECT
            (SELECT COUNT(*) FROM base) total,
            ARRAY(SELECT AS STRUCT id_despesa, id_clinica, nome_despesa, prestador,
              data_vencimento, mes_ano, status, valor_despesa, data_pagamento
              FROM base ORDER BY data_vencimento DESC, id_despesa DESC
              LIMIT @limit OFFSET @offset) items
        """, params))
        if not result:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}
        rows = [dict(row.items()) if hasattr(row, "items") else dict(row) for row in (result.get("items") or [])]
        return {"items": rows, "total": int(result.get("total") or 0), "page": page, "page_size": page_size}

    def list_consultations(self, clinic_id: int, search: str = "", date_from: str | None = None, date_to: str | None = None, doctor_id: int | None = None, status: str | None = None, page: int = 1, page_size: int = 25) -> dict:
        filters = []
        params = self._params(clinic=("INT64", clinic_id), search=("STRING", search), limit=("INT64", page_size), offset=("INT64", (page - 1) * page_size))
        if date_from:
            filters.append("AND c.data_consulta >= @date_from")
            params.append(bigquery.ScalarQueryParameter("date_from", "DATE", date_from))
        if date_to:
            filters.append("AND c.data_consulta <= @date_to")
            params.append(bigquery.ScalarQueryParameter("date_to", "DATE", date_to))
        if doctor_id is not None:
            filters.append("AND c.id_doutor = @doctor_id")
            params.append(bigquery.ScalarQueryParameter("doctor_id", "INT64", doctor_id))
        if status:
            filters.append("AND c.status = @status")
            params.append(bigquery.ScalarQueryParameter("status", "STRING", status))
        extra = "\n".join(filters)
        result = self._one(self._query(f"""
          WITH consultas AS (
            SELECT * FROM {self._trusted('consultas')}
            WHERE id_clinica = @clinic
            QUALIFY ROW_NUMBER() OVER(PARTITION BY id_consulta ORDER BY updated_at DESC, created_at DESC) = 1
          ),
          pacientes AS (
            SELECT * FROM {self._trusted('pacientes')}
            QUALIFY ROW_NUMBER() OVER(PARTITION BY id_paciente ORDER BY updated_at DESC, created_at DESC) = 1
          ),
          doutores AS (
            SELECT * FROM {self._trusted('doutores')}
            QUALIFY ROW_NUMBER() OVER(PARTITION BY id_doutor ORDER BY updated_at DESC, created_at DESC) = 1
          ),
          itens AS (
            SELECT id_consulta, id_clinica, COUNT(*) total_itens, SUM(valor_consulta) soma_itens
            FROM {self._trusted('consulta_procedimentos')}
            WHERE id_clinica = @clinic
            GROUP BY id_consulta, id_clinica
          ),
          base AS (
            SELECT
              c.id_consulta, c.id_clinica, c.id_paciente, c.id_doutor,
              COALESCE(p.nome_paciente, c.nome_paciente_origem) nome_paciente,
              COALESCE(d.nome_doutor, c.nome_doutor) nome_doutor,
              d.especialidade,
              c.data_consulta, c.status, c.valor_total,
              COALESCE(i.total_itens, 0) total_itens,
              i.soma_itens,
              c.flag_paciente_localizado,
              (c.valor_total IS NOT NULL AND i.soma_itens IS NOT NULL
               AND ROUND(CAST(c.valor_total AS NUMERIC), 2) != ROUND(CAST(i.soma_itens AS NUMERIC), 2)) divergencia_valor
            FROM consultas c
            LEFT JOIN pacientes p ON p.id_paciente = c.id_paciente
            LEFT JOIN doutores d ON d.id_doutor = c.id_doutor
            LEFT JOIN itens i ON i.id_consulta = c.id_consulta AND i.id_clinica = c.id_clinica
            WHERE (@search = '' OR CONTAINS_SUBSTR(
              LOWER(COALESCE(p.nome_paciente, c.nome_paciente_origem, '')), LOWER(@search)))
            {extra}
          )
          SELECT
            (SELECT COUNT(*) FROM base) total,
            ARRAY(SELECT AS STRUCT id_consulta, id_clinica, id_paciente, id_doutor,
              nome_paciente, nome_doutor, especialidade, data_consulta, status, valor_total,
              total_itens, soma_itens, flag_paciente_localizado, divergencia_valor
              FROM base ORDER BY data_consulta DESC, id_consulta DESC
              LIMIT @limit OFFSET @offset) items
        """, params))
        if not result:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}
        rows = [dict(row.items()) if hasattr(row, "items") else dict(row) for row in (result.get("items") or [])]
        return {"items": rows, "total": int(result.get("total") or 0), "page": page, "page_size": page_size}

    def get_consultation(self, clinic_id: int, consultation_id: int) -> dict | None:
        row = self._one(self._query(f"""
          WITH consultas AS (
            SELECT * FROM {self._trusted('consultas')}
            WHERE id_clinica = @clinic
            QUALIFY ROW_NUMBER() OVER(PARTITION BY id_consulta ORDER BY updated_at DESC, created_at DESC) = 1
          ),
          pacientes AS (
            SELECT * FROM {self._trusted('pacientes')}
            QUALIFY ROW_NUMBER() OVER(PARTITION BY id_paciente ORDER BY updated_at DESC, created_at DESC) = 1
          ),
          doutores AS (
            SELECT * FROM {self._trusted('doutores')}
            QUALIFY ROW_NUMBER() OVER(PARTITION BY id_doutor ORDER BY updated_at DESC, created_at DESC) = 1
          ),
          itens_agg AS (
            SELECT id_consulta, id_clinica, COUNT(*) total_itens, SUM(valor_consulta) soma_itens
            FROM {self._trusted('consulta_procedimentos')}
            WHERE id_clinica = @clinic AND id_consulta = @consultation
            GROUP BY id_consulta, id_clinica
          ),
          itens_list AS (
            SELECT id_consulta_procedimento, COALESCE(procedimento_tratado, procedimento_origem) nome_procedimento,
              elemento AS elemento_dental, descricao, valor_consulta
            FROM {self._trusted('consulta_procedimentos')}
            WHERE id_clinica = @clinic AND id_consulta = @consultation
            QUALIFY ROW_NUMBER() OVER(PARTITION BY id_consulta_procedimento ORDER BY updated_at DESC, created_at DESC) = 1
          )
          SELECT
            c.id_consulta, c.id_clinica, c.id_paciente, c.id_doutor,
            COALESCE(p.nome_paciente, c.nome_paciente_origem) nome_paciente,
            COALESCE(d.nome_doutor, c.nome_doutor) nome_doutor,
            d.especialidade,
            c.data_consulta, c.status, c.valor_total,
            COALESCE(a.total_itens, 0) total_itens,
            a.soma_itens,
            c.flag_paciente_localizado,
            c.tipo_match_paciente,
            c.nome_paciente_origem,
            (c.valor_total IS NOT NULL AND a.soma_itens IS NOT NULL
             AND ROUND(CAST(c.valor_total AS NUMERIC), 2) != ROUND(CAST(a.soma_itens AS NUMERIC), 2)) divergencia_valor,
            ARRAY(SELECT AS STRUCT id_consulta_procedimento, nome_procedimento, elemento_dental, descricao, valor_consulta FROM itens_list ORDER BY id_consulta_procedimento) itens
          FROM consultas c
          LEFT JOIN pacientes p ON p.id_paciente = c.id_paciente
          LEFT JOIN doutores d ON d.id_doutor = c.id_doutor
          LEFT JOIN itens_agg a ON a.id_consulta = c.id_consulta AND a.id_clinica = c.id_clinica
          WHERE c.id_consulta = @consultation
          LIMIT 1
        """, self._params(clinic=("INT64", clinic_id), consultation=("INT64", consultation_id))))
        if not row:
            return None
        itens_raw = row.get("itens") or []
        row["itens"] = [dict(i.items()) if hasattr(i, "items") else dict(i) for i in itens_raw]
        return row

    def list_doctors(self, clinic_id: int, search: str = "", active: bool | None = None, page: int = 1, page_size: int = 25) -> dict:
        active_sql = "" if active is None else "AND COALESCE(dc.flag_ativo, d.flag_ativo, TRUE) = @active"
        params = self._params(clinic=("INT64", clinic_id), search=("STRING", search), limit=("INT64", page_size), offset=("INT64", (page - 1) * page_size))
        if active is not None:
            params.append(bigquery.ScalarQueryParameter("active", "BOOL", active))
        result = self._one(self._query(f"""
          WITH doctors AS (
            SELECT * FROM {self._trusted('doutores')}
            QUALIFY ROW_NUMBER() OVER(PARTITION BY id_doutor ORDER BY updated_at DESC, created_at DESC) = 1
          ),
          links AS (
            SELECT * FROM {self._trusted('doutor_clinica')}
            WHERE id_clinica = @clinic
            QUALIFY ROW_NUMBER() OVER(PARTITION BY id_doutor ORDER BY updated_at DESC, created_at DESC) = 1
          ),
          counts AS (
            SELECT id_doutor, COUNT(*) total_consultas
            FROM {self._trusted('consultas')}
            WHERE id_clinica = @clinic AND id_doutor IS NOT NULL
            GROUP BY id_doutor
          ),
          base AS (
            SELECT
              d.id_doutor, dc.id_doutor_clinica, d.nome_doutor,
              d.especialidade, d.cro, d.cro_estado, d.percentual_repasse,
              COALESCE(dc.flag_ativo, d.flag_ativo, TRUE) flag_ativo,
              COALESCE(c.total_consultas, 0) total_consultas
            FROM doctors d
            JOIN links dc USING(id_doutor)
            LEFT JOIN counts c USING(id_doutor)
            WHERE (@search = '' OR CONTAINS_SUBSTR(LOWER(d.nome_doutor), LOWER(@search)))
            {active_sql}
          )
          SELECT
            (SELECT COUNT(*) FROM base) total,
            ARRAY(SELECT AS STRUCT id_doutor, id_doutor_clinica, nome_doutor, especialidade, cro, cro_estado, percentual_repasse, flag_ativo, total_consultas FROM base ORDER BY nome_doutor LIMIT @limit OFFSET @offset) items
        """, params))
        if not result:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}
        rows = [dict(row.items()) if hasattr(row, "items") else dict(row) for row in (result.get("items") or [])]
        return {"items": rows, "total": int(result.get("total") or 0), "page": page, "page_size": page_size}

    def get_doctor(self, clinic_id: int, doctor_id: int) -> dict | None:
        return self._one(self._query(f"""
          WITH doctors AS (
            SELECT * FROM {self._trusted('doutores')}
            QUALIFY ROW_NUMBER() OVER(PARTITION BY id_doutor ORDER BY updated_at DESC, created_at DESC) = 1
          ),
          links AS (
            SELECT * FROM {self._trusted('doutor_clinica')}
            WHERE id_clinica = @clinic
            QUALIFY ROW_NUMBER() OVER(PARTITION BY id_doutor ORDER BY updated_at DESC, created_at DESC) = 1
          )
          SELECT
            d.id_doutor, dc.id_doutor_clinica, @clinic AS id_clinica, d.nome_doutor,
            d.especialidade, d.cro, d.cro_estado, d.percentual_repasse,
            COALESCE(dc.flag_ativo, d.flag_ativo, TRUE) flag_ativo,
            CAST(dc.data_inicio AS DATETIME) data_inicio,
            dc.data_fim,
            (SELECT COUNT(*) FROM {self._trusted('consultas')} WHERE id_clinica = @clinic AND id_doutor = d.id_doutor) total_consultas
          FROM doctors d
          JOIN links dc USING(id_doutor)
          WHERE d.id_doutor = @doctor
          LIMIT 1
        """, self._params(clinic=("INT64", clinic_id), doctor=("INT64", doctor_id))))

    def audit(self, actor_id, organization_id, clinic_id, action, entity, entity_id):
        audit = self._unique_id(self._bc("auditoria"), "id_auditoria")
        self._query(f"INSERT INTO {self._bc('auditoria')} VALUES (@id,@actor,@org,@clinic,@action,@entity,@entity_id,CURRENT_TIMESTAMP())", self._params(id=("INT64", audit), actor=("INT64", actor_id), org=("INT64", organization_id), clinic=("INT64", clinic_id), action=("STRING", action), entity=("STRING", entity), entity_id=("INT64", entity_id)))
