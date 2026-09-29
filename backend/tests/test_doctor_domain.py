"""
Tests for the Doctor-Clinic backfill domain logic.

These tests cover the pure Python logic that computes which (id_doutor, id_clinica)
pairs need to be inserted into doutor_clinica. They do not touch BigQuery or Firebase.

The SQL backfill (016_doctor_clinic_backfill.sql) must match this logic exactly.
"""
from __future__ import annotations


def compute_backfill_pairs(
    doutores: list[dict],
    consultas: list[dict],
    existing_pairs: set[tuple[int, int]],
) -> list[dict]:
    """
    Pure logic: return the new (id_doutor, id_clinica) pairs to insert.

    Wave 1 — pairs from doutores.id_clinica not already in doutor_clinica.
    Wave 2 — pairs from consultas (distinct id_doutor, id_clinica) not covered
              by existing_pairs or wave 1.

    Returns a list of dicts with keys: id_doutor, id_clinica, origem.
    """
    new_pairs: list[dict] = []
    seen: set[tuple[int, int]] = set(existing_pairs)

    # Wave 1
    for d in doutores:
        if d.get("id_clinica") is None:
            continue
        pair = (d["id_doutor"], d["id_clinica"])
        if pair not in seen:
            new_pairs.append({"id_doutor": d["id_doutor"], "id_clinica": d["id_clinica"], "origem": "WAVE1"})
            seen.add(pair)

    # Wave 2
    for c in consultas:
        if c.get("id_doutor") is None:
            continue
        pair = (c["id_doutor"], c["id_clinica"])
        if pair not in seen:
            new_pairs.append({"id_doutor": c["id_doutor"], "id_clinica": c["id_clinica"], "origem": "WAVE2"})
            seen.add(pair)

    return new_pairs


def reconcile_doctors(
    doutores: list[dict],
    doutor_clinica: list[dict],
    consultas: list[dict],
) -> dict:
    """
    Returns reconciliation counts matching 017_doctor_clinic_reconciliation.sql checks.
    All acceptance-criteria values must be zero.
    """
    dc_pairs = {(r["id_doutor"], r["id_clinica"]) for r in doutor_clinica}
    consulta_pairs = {(c["id_doutor"], c["id_clinica"]) for c in consultas if c.get("id_doutor")}
    doutor_ids = {d["id_doutor"] for d in doutores}
    dc_pair_counts: dict[tuple, int] = {}
    for r in doutor_clinica:
        k = (r["id_doutor"], r["id_clinica"])
        dc_pair_counts[k] = dc_pair_counts.get(k, 0) + 1

    return {
        "duplicate_pairs": sum(1 for v in dc_pair_counts.values() if v > 1),
        "doctors_without_link": sum(1 for d in doutores if not any(r["id_doutor"] == d["id_doutor"] for r in doutor_clinica)),
        "consultations_without_link": len(consulta_pairs - dc_pairs),
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_wave1_inserts_missing_pairs_from_doutores_id_clinica():
    doutores = [
        {"id_doutor": 1, "id_clinica": 10},
        {"id_doutor": 2, "id_clinica": 10},
    ]
    result = compute_backfill_pairs(doutores, [], existing_pairs=set())
    assert len(result) == 2
    assert all(r["origem"] == "WAVE1" for r in result)


def test_wave1_skips_pairs_already_in_doutor_clinica():
    doutores = [{"id_doutor": 1, "id_clinica": 10}]
    result = compute_backfill_pairs(doutores, [], existing_pairs={(1, 10)})
    assert result == []


def test_wave2_inserts_pairs_from_consultas_not_in_wave1_or_existing():
    doutores = [{"id_doutor": 1, "id_clinica": 10}]
    consultas = [
        {"id_doutor": 1, "id_clinica": 20},  # different clinic
        {"id_doutor": 2, "id_clinica": 10},  # different doctor
    ]
    result = compute_backfill_pairs(doutores, consultas, existing_pairs=set())
    # Wave1 covers (1,10); wave2 covers (1,20) and (2,10)
    assert len(result) == 3
    wave2 = [r for r in result if r["origem"] == "WAVE2"]
    assert len(wave2) == 2


def test_backfill_is_idempotent_when_run_twice():
    doutores = [{"id_doutor": 1, "id_clinica": 10}]
    consultas = [{"id_doutor": 1, "id_clinica": 20}]

    first_run = compute_backfill_pairs(doutores, consultas, existing_pairs=set())
    inserted = {(r["id_doutor"], r["id_clinica"]) for r in first_run}

    second_run = compute_backfill_pairs(doutores, consultas, existing_pairs=inserted)
    assert second_run == [], "second run must produce no new pairs (idempotent)"


def test_backfill_skips_doctors_without_id_clinica():
    doutores = [{"id_doutor": 1, "id_clinica": None}]
    result = compute_backfill_pairs(doutores, [], existing_pairs=set())
    assert result == []


def test_backfill_skips_consultas_without_id_doutor():
    consultas = [{"id_doutor": None, "id_clinica": 10}]
    result = compute_backfill_pairs([], consultas, existing_pairs=set())
    assert result == []


def test_wave2_does_not_duplicate_pair_already_inserted_by_wave1():
    doutores = [{"id_doutor": 1, "id_clinica": 10}]
    consultas = [{"id_doutor": 1, "id_clinica": 10}]  # same pair as wave1
    result = compute_backfill_pairs(doutores, consultas, existing_pairs=set())
    pairs = [(r["id_doutor"], r["id_clinica"]) for r in result]
    assert pairs.count((1, 10)) == 1, "pair must appear exactly once"


def test_wave2_does_not_duplicate_pair_seen_in_multiple_consultas():
    doutores = []
    consultas = [
        {"id_doutor": 2, "id_clinica": 10},
        {"id_doutor": 2, "id_clinica": 10},
        {"id_doutor": 2, "id_clinica": 10},
    ]
    result = compute_backfill_pairs(doutores, consultas, existing_pairs=set())
    assert len(result) == 1


def test_reconciliation_passes_when_all_criteria_met():
    doutores = [{"id_doutor": 1}, {"id_doutor": 2}]
    doutor_clinica = [
        {"id_doutor": 1, "id_clinica": 10},
        {"id_doutor": 2, "id_clinica": 10},
    ]
    consultas = [
        {"id_doutor": 1, "id_clinica": 10},
        {"id_doutor": 2, "id_clinica": 10},
    ]
    result = reconcile_doctors(doutores, doutor_clinica, consultas)
    assert result["duplicate_pairs"] == 0
    assert result["doctors_without_link"] == 0
    assert result["consultations_without_link"] == 0


def test_reconciliation_detects_duplicate_pairs():
    doutores = [{"id_doutor": 1}]
    doutor_clinica = [
        {"id_doutor": 1, "id_clinica": 10},
        {"id_doutor": 1, "id_clinica": 10},  # duplicate
    ]
    result = reconcile_doctors(doutores, doutor_clinica, [])
    assert result["duplicate_pairs"] == 1


def test_reconciliation_detects_doctor_without_any_link():
    doutores = [{"id_doutor": 1}, {"id_doutor": 2}]
    doutor_clinica = [{"id_doutor": 1, "id_clinica": 10}]  # doutor 2 missing
    result = reconcile_doctors(doutores, doutor_clinica, [])
    assert result["doctors_without_link"] == 1


def test_reconciliation_detects_consultation_without_link():
    doutores = [{"id_doutor": 1}]
    doutor_clinica = [{"id_doutor": 1, "id_clinica": 10}]
    consultas = [
        {"id_doutor": 1, "id_clinica": 10},  # covered
        {"id_doutor": 1, "id_clinica": 20},  # not covered
    ]
    result = reconcile_doctors(doutores, doutor_clinica, consultas)
    assert result["consultations_without_link"] == 1


def test_reconciliation_ignores_consultas_without_id_doutor():
    doutores = [{"id_doutor": 1}]
    doutor_clinica = [{"id_doutor": 1, "id_clinica": 10}]
    consultas = [
        {"id_doutor": None, "id_clinica": 10},  # no doctor, must be ignored
    ]
    result = reconcile_doctors(doutores, doutor_clinica, consultas)
    assert result["consultations_without_link"] == 0


def test_full_scenario_matching_validation_dataset_state():
    """
    Mirrors the state described in the data map (2026-09-29):
    5 doctors, 1 existing doutor_clinica record, 201 consultations
    with 4 doctors lacking any link in the bridge.
    After backfill: zero doctors without link, zero consultations with id_doutor unlinked.
    """
    doutores = [
        {"id_doutor": i, "id_clinica": 1}  # all historically attached to clinic 1
        for i in range(1, 6)
    ]
    existing = {(1, 1)}  # only doctor 1 has a record

    # 97 consultations reference a doctor but have no pair in the bridge
    consultas = [
        {"id_doutor": (i % 5) + 1, "id_clinica": 1}
        for i in range(97)
    ]

    new_pairs = compute_backfill_pairs(doutores, consultas, existing_pairs=existing)
    all_pairs = existing | {(r["id_doutor"], r["id_clinica"]) for r in new_pairs}

    doutor_clinica_after = [{"id_doutor": d, "id_clinica": c} for d, c in all_pairs]
    result = reconcile_doctors(doutores, doutor_clinica_after, consultas)

    assert result["duplicate_pairs"] == 0
    assert result["doctors_without_link"] == 0
    assert result["consultations_without_link"] == 0
