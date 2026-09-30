"""
Pure Python tests for the consultation list/detail service logic.

These tests do not touch BigQuery or Firebase. They exercise the service-layer
validation rules (permission check, 404 handling, filters) and pagination arithmetic.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Minimal stubs
# ---------------------------------------------------------------------------

class _FakeRepo:
    """Test stub that returns pre-configured data without any I/O."""

    def __init__(self, *, consultations: list[dict] | None = None, has_perm: bool = True):
        self._consultations = consultations or []
        self._has_perm = has_perm
        self.calls: list[tuple] = []

    def resolve_identity(self, user):
        return {"id_usuario": 1, "id_organizacao": 1, "ativo": True, "troca_senha_obrigatoria": False, "perfis": [], "permissoes": []}

    def has_permission(self, user_id, clinic_id, permission):
        return self._has_perm

    def list_consultations(self, clinic_id, search, date_from, date_to, doctor_id, status, page, page_size):
        self.calls.append(("list_consultations", clinic_id, search, date_from, date_to, doctor_id, status, page, page_size))
        items = self._consultations
        if search:
            items = [c for c in items if search.lower() in (c.get("nome_paciente") or "").lower()]
        if doctor_id is not None:
            items = [c for c in items if c.get("id_doutor") == doctor_id]
        if status:
            items = [c for c in items if c.get("status") == status]
        total = len(items)
        offset = (page - 1) * page_size
        return {"items": items[offset:offset + page_size], "total": total, "page": page, "page_size": page_size}

    def get_consultation(self, clinic_id, consultation_id):
        self.calls.append(("get_consultation", clinic_id, consultation_id))
        for c in self._consultations:
            if c["id_consulta"] == consultation_id:
                return {**c, "tipo_match_paciente": None, "nome_paciente_origem": None, "itens": []}
        return None

    # Unused protocol stubs
    def bootstrap(self, *a, **kw): ...
    def count_organization_clinics(self, *a, **kw): return 0
    def create_clinic(self, *a, **kw): ...
    def create_patient_with_link(self, *a, **kw): ...
    def get_create_patient_result(self, *a, **kw): return None
    def get_patient_by_cpf(self, *a, **kw): return None
    def has_patient_link(self, *a, **kw): return False
    def link_patient(self, *a, **kw): ...
    def get_form(self, *a, **kw): return None
    def submit_anamnesis(self, *a, **kw): ...
    def list_clinics(self, *a, **kw): return []
    def list_doctors(self, *a, **kw): return {"items": [], "total": 0, "page": 1, "page_size": 25}
    def get_doctor(self, *a, **kw): return None


class _FakeUser:
    firebase_uid = "uid-test"
    email = "test@example.com"


_USER = _FakeUser()

SAMPLE_CONSULTATIONS = [
    {
        "id_consulta": 1, "id_clinica": 10, "id_paciente": 100, "id_doutor": 5,
        "nome_paciente": "Ana Lima", "nome_doutor": "Dr. Bruno", "especialidade": "Ortodontia",
        "data_consulta": "2024-01-15", "status": "FINALIZADA", "valor_total": 300.0,
        "total_itens": 2, "soma_itens": 300.0, "flag_paciente_localizado": True, "divergencia_valor": False,
    },
    {
        "id_consulta": 2, "id_clinica": 10, "id_paciente": None, "id_doutor": 5,
        "nome_paciente": "Carlos Origem", "nome_doutor": "Dr. Bruno", "especialidade": "Ortodontia",
        "data_consulta": "2024-02-10", "status": "FINALIZADA", "valor_total": 500.0,
        "total_itens": 3, "soma_itens": 650.0, "flag_paciente_localizado": False, "divergencia_valor": True,
    },
    {
        "id_consulta": 3, "id_clinica": 10, "id_paciente": 101, "id_doutor": 6,
        "nome_paciente": "Diana Souza", "nome_doutor": "Dra. Eva", "especialidade": "Endodontia",
        "data_consulta": "2024-03-01", "status": "FINALIZADA", "valor_total": None,
        "total_itens": 0, "soma_itens": None, "flag_paciente_localizado": True, "divergencia_valor": False,
    },
]


def _svc(consultations=None, has_perm=True):
    from app.services.mvp import MvpService
    return MvpService(_FakeRepo(consultations=consultations, has_perm=has_perm))


# ---------------------------------------------------------------------------
# list_consultations — authorization
# ---------------------------------------------------------------------------

def test_list_consultations_raises_if_no_permission():
    from app.core import BusinessError
    svc = _svc(consultations=SAMPLE_CONSULTATIONS, has_perm=False)
    with pytest.raises(BusinessError) as exc_info:
        svc.list_consultations(_USER, clinic_id=10)
    assert exc_info.value.code == "FORBIDDEN"


def test_list_consultations_returns_paginated_result_when_authorized():
    svc = _svc(consultations=SAMPLE_CONSULTATIONS)
    result = svc.list_consultations(_USER, clinic_id=10)
    assert result["total"] == 3
    assert len(result["items"]) == 3
    assert result["page"] == 1


# ---------------------------------------------------------------------------
# list_consultations — filtering
# ---------------------------------------------------------------------------

def test_list_consultations_search_filters_by_patient_name():
    svc = _svc(consultations=SAMPLE_CONSULTATIONS)
    result = svc.list_consultations(_USER, clinic_id=10, search="ana lima")
    assert result["total"] == 1
    assert result["items"][0]["nome_paciente"] == "Ana Lima"


def test_list_consultations_doctor_filter():
    svc = _svc(consultations=SAMPLE_CONSULTATIONS)
    result = svc.list_consultations(_USER, clinic_id=10, doctor_id=6)
    assert result["total"] == 1
    assert result["items"][0]["id_doutor"] == 6


def test_list_consultations_status_filter():
    svc = _svc(consultations=SAMPLE_CONSULTATIONS)
    result = svc.list_consultations(_USER, clinic_id=10, status="FINALIZADA")
    assert result["total"] == 3


def test_list_consultations_empty_clinic_returns_empty():
    svc = _svc(consultations=[])
    result = svc.list_consultations(_USER, clinic_id=99)
    assert result["items"] == []
    assert result["total"] == 0


# ---------------------------------------------------------------------------
# list_consultations — pagination
# ---------------------------------------------------------------------------

def test_list_consultations_pagination_page_size():
    svc = _svc(consultations=SAMPLE_CONSULTATIONS)
    result = svc.list_consultations(_USER, clinic_id=10, page=1, page_size=2)
    assert len(result["items"]) == 2
    assert result["total"] == 3
    assert result["page_size"] == 2


def test_list_consultations_pagination_second_page():
    svc = _svc(consultations=SAMPLE_CONSULTATIONS)
    result = svc.list_consultations(_USER, clinic_id=10, page=2, page_size=2)
    assert len(result["items"]) == 1
    assert result["page"] == 2


# ---------------------------------------------------------------------------
# list_consultations — divergencia_valor field
# ---------------------------------------------------------------------------

def test_list_consultations_divergencia_valor_is_present():
    svc = _svc(consultations=SAMPLE_CONSULTATIONS)
    result = svc.list_consultations(_USER, clinic_id=10)
    divergent = [c for c in result["items"] if c["divergencia_valor"]]
    assert len(divergent) == 1
    assert divergent[0]["id_consulta"] == 2


# ---------------------------------------------------------------------------
# get_consultation — authorization and 404
# ---------------------------------------------------------------------------

def test_get_consultation_raises_if_no_permission():
    from app.core import BusinessError
    svc = _svc(consultations=SAMPLE_CONSULTATIONS, has_perm=False)
    with pytest.raises(BusinessError) as exc_info:
        svc.get_consultation(_USER, clinic_id=10, consultation_id=1)
    assert exc_info.value.code == "FORBIDDEN"


def test_get_consultation_raises_404_when_not_found():
    from app.core import BusinessError
    svc = _svc(consultations=SAMPLE_CONSULTATIONS)
    with pytest.raises(BusinessError) as exc_info:
        svc.get_consultation(_USER, clinic_id=10, consultation_id=999)
    assert exc_info.value.code == "CONSULTATION_NOT_FOUND"
    assert exc_info.value.status_code == 404


def test_get_consultation_returns_detail_when_found():
    svc = _svc(consultations=SAMPLE_CONSULTATIONS)
    result = svc.get_consultation(_USER, clinic_id=10, consultation_id=1)
    assert result["id_consulta"] == 1
    assert result["nome_paciente"] == "Ana Lima"
    assert "itens" in result


def test_get_consultation_includes_divergence_and_quality_fields():
    svc = _svc(consultations=SAMPLE_CONSULTATIONS)
    result = svc.get_consultation(_USER, clinic_id=10, consultation_id=2)
    assert result["divergencia_valor"] is True
    assert result["flag_paciente_localizado"] is False
    assert "tipo_match_paciente" in result
    assert "nome_paciente_origem" in result


def test_get_consultation_forwards_correct_ids_to_repo():
    repo = _FakeRepo(consultations=SAMPLE_CONSULTATIONS)
    from app.services.mvp import MvpService
    svc = MvpService(repo)
    svc.get_consultation(_USER, clinic_id=10, consultation_id=3)
    assert ("get_consultation", 10, 3) in repo.calls


def test_list_consultations_forwards_correct_params_to_repo():
    repo = _FakeRepo(consultations=SAMPLE_CONSULTATIONS)
    from app.services.mvp import MvpService
    svc = MvpService(repo)
    svc.list_consultations(_USER, clinic_id=10, search="ana", date_from="2024-01-01", date_to="2024-12-31", doctor_id=5, status="FINALIZADA", page=2, page_size=10)
    assert ("list_consultations", 10, "ana", "2024-01-01", "2024-12-31", 5, "FINALIZADA", 2, 10) in repo.calls
