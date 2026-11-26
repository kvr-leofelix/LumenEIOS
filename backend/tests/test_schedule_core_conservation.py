"""Recovery must never silently downgrade or drop Core: the server checks the actual Core slots, not only the declared counts."""
import copy

from backend.app.services.schedule_validation import validate_schedule

CFG = {"start": "2026-11-16", "end": "2026-11-20", "weekdays": [1, 2, 3, 4, 5], "entries": [], "subjectPeriodsPerDay": {"Science": 2}, "periodsPerDay": 8}


def lesson(node, slots, core=2, non=1, core_unscheduled=0):
    return {"nodeId": node, "corePeriods": core, "nonCorePeriods": non, "requiredPeriods": core + non, "coreUnscheduled": core_unscheduled,
            "slots": [{"date": d, "period": p, "kind": k} for d, p, k in slots]}


V1 = [lesson("a", [("2026-11-16", 1, "CORE"), ("2026-11-16", 2, "CORE"), ("2026-11-17", 1, "NON_CORE")])]


def test_identical_schedule_is_valid():
    assert validate_schedule(copy.deepcopy(V1), CFG, "Science", V1, "p") == []


def test_flipping_a_core_slot_to_non_core_is_rejected_even_if_declared_counts_stay():
    bad = copy.deepcopy(V1)
    bad[0]["slots"][0]["kind"] = "NON_CORE"
    problems = validate_schedule(bad, CFG, "Science", V1, "p")
    assert any("Core periods were silently reduced" in p for p in problems)


def test_unrecovered_core_is_allowed_only_when_reported_as_unscheduled():
    unresolved = [lesson("a", [("2026-11-16", 2, "CORE"), ("2026-11-17", 1, "NON_CORE")], core_unscheduled=1)]
    assert validate_schedule(unresolved, CFG, "Science", V1, "p") == []
    silent = [lesson("a", [("2026-11-16", 2, "CORE"), ("2026-11-17", 1, "NON_CORE")])]
    assert validate_schedule(silent, CFG, "Science", V1, "p") != []
