"""
Pure Python tests for the doctor list/detail service logic.

These tests do not touch BigQuery or Firebase. They exercise the service-layer
validation rules (permission check, 404 handling) and the pagination arithmetic
that mirrors list_doctors() in BigQueryMvpRepository.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Minimal stubs
# ---------------------------------------------------------------------------

class _FakeRepo:
    """Test stub that returns pre-configured data without any I/O."""

    def __init__(self, *, doctors: list[dict] | None = None, has_perm: bool = True):
        self._doctors = doctors or []
        self._has_perm = has_perm
        self.calls: list[tuple] = []

    # Protocol surface used by MvpService
    def resolve_identity(self, user):
        return {"id_usuario": 1, "id_organizacao": 1, "ativo": True, "troca_senha_obrigatoria": False, "perfis": [], "permissoes": []}

    def has_permission(self, user_id, clinic_id, permission):
        return self._has_perm

    def list_doctors(self, clinic_id, search, active, page, page_size):
        self.calls.append(("list_doctors", clinic_id, search, active, page, page_size))
        items = self._doctors
        if search:
            items = [d for d in items if search.lower() in d.get("nome_doutor", "").lower()]
        if active is not None:
            items = [d for d in items if d.get("flag_ativo", True) == active]
        total = len(items)
        offset = (page - 1) * page_size
        return {"items": items[offset:offset + page_size], "total": total, "page": page, "page_size": page_size}

    def get_doctor(self, clinic_id, doctor_id):
        self.calls.append(("get_doctor", clinic_id, doctor_id))
        for d in self._doctors:
            if d["id_doutor"] == doctor_id:
                return {**d, "id_clinica": clinic_id, "data_inicio": None, "data_fim": None}
        return None

    # Unused protocol stubs (required by Protocol)
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


class _FakeUser:
    firebase_uid = "uid-test"
    email = "test@example.com"


_USER = _FakeUser()

SAMPLE_DOCTORS = [
    {"id_doutor": 1, "id_doutor_clinica": 101, "nome_doutor": "Ana Silva", "especialidade": "Ortodontia", "cro": "12345", "cro_estado": "SP", "percentual_repasse": 60.0, "flag_ativo": True, "total_consultas": 50},
    {"id_doutor": 2, "id_doutor_clinica": 102, "nome_doutor": "Bruno Costa", "especialidade": "Endodontia", "cro": "67890", "cro_estado": "SP", "percentual_repasse": 55.0, "flag_ativo": True, "total_consultas": 30},
    {"id_doutor": 3, "id_doutor_clinica": 103, "nome_doutor": "Carla Melo", "especialidade": "Ortodontia", "cro": "11111", "cro_estado": "RJ", "percentual_repasse": 50.0, "flag_ativo": False, "total_consultas": 10},
]


def _svc(doctors=None, has_perm=True):
    from app.services.mvp import MvpService
    return MvpService(_FakeRepo(doctors=doctors, has_perm=has_perm))


# ---------------------------------------------------------------------------
# list_doctors — authorization
# ---------------------------------------------------------------------------

def test_list_doctors_raises_if_no_permission():
    from app.core import BusinessError
    svc = _svc(doctors=SAMPLE_DOCTORS, has_perm=False)
    with pytest.raises(BusinessError) as exc_info:
        svc.list_doctors(_USER, clinic_id=1)
    assert exc_info.value.code == "FORBIDDEN"


def test_list_doctors_returns_paginated_result_when_authorized():
    svc = _svc(doctors=SAMPLE_DOCTORS)
    result = svc.list_doctors(_USER, clinic_id=1)
    assert result["total"] == 3
    assert len(result["items"]) == 3
    assert result["page"] == 1


# ---------------------------------------------------------------------------
# list_doctors — filtering
# ---------------------------------------------------------------------------

def test_list_doctors_search_filters_by_name():
    svc = _svc(doctors=SAMPLE_DOCTORS)
    result = svc.list_doctors(_USER, clinic_id=1, search="ana")
    assert result["total"] == 1
    assert result["items"][0]["nome_doutor"] == "Ana Silva"


def test_list_doctors_active_filter_true_returns_only_active():
    svc = _svc(doctors=SAMPLE_DOCTORS)
    result = svc.list_doctors(_USER, clinic_id=1, active=True)
    assert all(d["flag_ativo"] for d in result["items"])
    assert result["total"] == 2


def test_list_doctors_active_filter_false_returns_only_inactive():
    svc = _svc(doctors=SAMPLE_DOCTORS)
    result = svc.list_doctors(_USER, clinic_id=1, active=False)
    assert all(not d["flag_ativo"] for d in result["items"])
    assert result["total"] == 1


def test_list_doctors_active_none_returns_all():
    svc = _svc(doctors=SAMPLE_DOCTORS)
    result = svc.list_doctors(_USER, clinic_id=1, active=None)
    assert result["total"] == 3


# ---------------------------------------------------------------------------
# list_doctors — pagination
# ---------------------------------------------------------------------------

def test_list_doctors_pagination_page_size():
    svc = _svc(doctors=SAMPLE_DOCTORS)
    result = svc.list_doctors(_USER, clinic_id=1, page=1, page_size=2)
    assert len(result["items"]) == 2
    assert result["total"] == 3
    assert result["page"] == 1
    assert result["page_size"] == 2


def test_list_doctors_pagination_second_page():
    svc = _svc(doctors=SAMPLE_DOCTORS)
    result = svc.list_doctors(_USER, clinic_id=1, page=2, page_size=2)
    assert len(result["items"]) == 1
    assert result["page"] == 2


def test_list_doctors_empty_clinic_returns_empty():
    svc = _svc(doctors=[])
    result = svc.list_doctors(_USER, clinic_id=99)
    assert result["items"] == []
    assert result["total"] == 0


# ---------------------------------------------------------------------------
# get_doctor — authorization and 404
# ---------------------------------------------------------------------------

def test_get_doctor_raises_if_no_permission():
    from app.core import BusinessError
    svc = _svc(doctors=SAMPLE_DOCTORS, has_perm=False)
    with pytest.raises(BusinessError) as exc_info:
        svc.get_doctor(_USER, clinic_id=1, doctor_id=1)
    assert exc_info.value.code == "FORBIDDEN"


def test_get_doctor_raises_404_when_not_found():
    from app.core import BusinessError
    svc = _svc(doctors=SAMPLE_DOCTORS)
    with pytest.raises(BusinessError) as exc_info:
        svc.get_doctor(_USER, clinic_id=1, doctor_id=999)
    assert exc_info.value.code == "DOCTOR_NOT_FOUND"
    assert exc_info.value.status_code == 404


def test_get_doctor_returns_detail_when_found():
    svc = _svc(doctors=SAMPLE_DOCTORS)
    result = svc.get_doctor(_USER, clinic_id=1, doctor_id=1)
    assert result["id_doutor"] == 1
    assert result["nome_doutor"] == "Ana Silva"
    assert result["id_clinica"] == 1


def test_get_doctor_includes_clinic_and_period_fields():
    svc = _svc(doctors=SAMPLE_DOCTORS)
    result = svc.get_doctor(_USER, clinic_id=1, doctor_id=2)
    assert "id_clinica" in result
    assert "data_inicio" in result
    assert "data_fim" in result


def test_get_doctor_forwards_correct_ids_to_repo():
    repo = _FakeRepo(doctors=SAMPLE_DOCTORS)
    from app.services.mvp import MvpService
    svc = MvpService(repo)
    svc.get_doctor(_USER, clinic_id=5, doctor_id=3)
    assert ("get_doctor", 5, 3) in repo.calls


def test_list_doctors_forwards_correct_clinic_id_to_repo():
    repo = _FakeRepo(doctors=SAMPLE_DOCTORS)
    from app.services.mvp import MvpService
    svc = MvpService(repo)
    svc.list_doctors(_USER, clinic_id=7, search="", active=None, page=2, page_size=10)
    assert ("list_doctors", 7, "", None, 2, 10) in repo.calls
