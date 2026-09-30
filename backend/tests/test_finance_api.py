"""
Pure Python tests for the financial summary and expense list service logic.

No BigQuery or Firebase — exercises permission checks, period filters,
summary arithmetic, and pagination.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Minimal stubs
# ---------------------------------------------------------------------------

class _FakeRepo:
    def __init__(self, *, expenses: list[dict] | None = None, summary: dict | None = None, has_perm: bool = True):
        self._expenses = expenses or []
        self._summary = summary or {"producao_estimada": 1000.0, "total_despesas": 400.0, "resultado_estimado": 600.0, "total_consultas": 5, "total_despesas_count": 3}
        self._has_perm = has_perm
        self.calls: list[tuple] = []

    def resolve_identity(self, user):
        return {"id_usuario": 1, "id_organizacao": 1, "ativo": True, "troca_senha_obrigatoria": False, "perfis": [], "permissoes": []}

    def has_permission(self, user_id, clinic_id, permission):
        return self._has_perm

    def get_financial_summary(self, clinic_id, mes_ano):
        self.calls.append(("get_financial_summary", clinic_id, mes_ano))
        return self._summary

    def list_expenses(self, clinic_id, mes_ano, page, page_size):
        self.calls.append(("list_expenses", clinic_id, mes_ano, page, page_size))
        items = self._expenses
        if mes_ano:
            items = [e for e in items if e.get("mes_ano") == mes_ano]
        total = len(items)
        offset = (page - 1) * page_size
        return {"items": items[offset:offset + page_size], "total": total, "page": page, "page_size": page_size}

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
    def list_consultations(self, *a, **kw): return {"items": [], "total": 0, "page": 1, "page_size": 25}
    def get_consultation(self, *a, **kw): return None


class _FakeUser:
    firebase_uid = "uid-test"
    email = "test@example.com"


_USER = _FakeUser()

SAMPLE_EXPENSES = [
    {"id_despesa": 1, "id_clinica": 10, "nome_despesa": "Aluguel", "prestador": "Imob SA", "data_vencimento": "2024-01-05", "mes_ano": "2024-01", "status": "OK", "valor_despesa": 2000.0, "data_pagamento": "2024-01-05"},
    {"id_despesa": 2, "id_clinica": 10, "nome_despesa": "Energia", "prestador": "CPFL", "data_vencimento": "2024-01-15", "mes_ano": "2024-01", "status": "OK", "valor_despesa": 350.0, "data_pagamento": "2024-01-15"},
    {"id_despesa": 3, "id_clinica": 10, "nome_despesa": "Material", "prestador": "Dental Shop", "data_vencimento": "2024-02-10", "mes_ano": "2024-02", "status": "NOK", "valor_despesa": 800.0, "data_pagamento": None},
]


def _svc(expenses=None, summary=None, has_perm=True):
    from app.services.mvp import MvpService
    return MvpService(_FakeRepo(expenses=expenses, summary=summary, has_perm=has_perm))


# ---------------------------------------------------------------------------
# get_financial_summary — authorization
# ---------------------------------------------------------------------------

def test_financial_summary_raises_if_no_permission():
    from app.core import BusinessError
    svc = _svc(has_perm=False)
    with pytest.raises(BusinessError) as exc_info:
        svc.get_financial_summary(_USER, clinic_id=10)
    assert exc_info.value.code == "FORBIDDEN"


def test_financial_summary_returns_result_when_authorized():
    svc = _svc()
    result = svc.get_financial_summary(_USER, clinic_id=10)
    assert "producao_estimada" in result
    assert "total_despesas" in result
    assert "resultado_estimado" in result
    assert "total_consultas" in result


def test_financial_summary_resultado_equals_producao_minus_despesas():
    summary = {"producao_estimada": 5000.0, "total_despesas": 1500.0, "resultado_estimado": 3500.0, "total_consultas": 10, "total_despesas_count": 5}
    svc = _svc(summary=summary)
    result = svc.get_financial_summary(_USER, clinic_id=10)
    assert result["resultado_estimado"] == result["producao_estimada"] - result["total_despesas"]


def test_financial_summary_forwards_mes_ano_to_repo():
    repo = _FakeRepo()
    from app.services.mvp import MvpService
    svc = MvpService(repo)
    svc.get_financial_summary(_USER, clinic_id=10, mes_ano="2024-01")
    assert ("get_financial_summary", 10, "2024-01") in repo.calls


def test_financial_summary_mes_ano_none_when_not_provided():
    repo = _FakeRepo()
    from app.services.mvp import MvpService
    svc = MvpService(repo)
    svc.get_financial_summary(_USER, clinic_id=10)
    assert ("get_financial_summary", 10, None) in repo.calls


# ---------------------------------------------------------------------------
# list_expenses — authorization
# ---------------------------------------------------------------------------

def test_list_expenses_raises_if_no_permission():
    from app.core import BusinessError
    svc = _svc(expenses=SAMPLE_EXPENSES, has_perm=False)
    with pytest.raises(BusinessError) as exc_info:
        svc.list_expenses(_USER, clinic_id=10)
    assert exc_info.value.code == "FORBIDDEN"


def test_list_expenses_returns_paginated_result():
    svc = _svc(expenses=SAMPLE_EXPENSES)
    result = svc.list_expenses(_USER, clinic_id=10)
    assert result["total"] == 3
    assert len(result["items"]) == 3


def test_list_expenses_period_filter():
    svc = _svc(expenses=SAMPLE_EXPENSES)
    result = svc.list_expenses(_USER, clinic_id=10, mes_ano="2024-01")
    assert result["total"] == 2
    assert all(e["mes_ano"] == "2024-01" for e in result["items"])


def test_list_expenses_pagination():
    svc = _svc(expenses=SAMPLE_EXPENSES)
    result = svc.list_expenses(_USER, clinic_id=10, page=1, page_size=2)
    assert len(result["items"]) == 2
    assert result["total"] == 3


def test_list_expenses_second_page():
    svc = _svc(expenses=SAMPLE_EXPENSES)
    result = svc.list_expenses(_USER, clinic_id=10, page=2, page_size=2)
    assert len(result["items"]) == 1
    assert result["page"] == 2


def test_list_expenses_empty():
    svc = _svc(expenses=[])
    result = svc.list_expenses(_USER, clinic_id=99)
    assert result["items"] == []
    assert result["total"] == 0


def test_list_expenses_preserves_status_codes():
    svc = _svc(expenses=SAMPLE_EXPENSES)
    result = svc.list_expenses(_USER, clinic_id=10)
    statuses = {e["status"] for e in result["items"]}
    assert "OK" in statuses
    assert "NOK" in statuses


def test_list_expenses_forwards_correct_params_to_repo():
    repo = _FakeRepo(expenses=SAMPLE_EXPENSES)
    from app.services.mvp import MvpService
    svc = MvpService(repo)
    svc.list_expenses(_USER, clinic_id=10, mes_ano="2024-02", page=2, page_size=10)
    assert ("list_expenses", 10, "2024-02", 2, 10) in repo.calls
