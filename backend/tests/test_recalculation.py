"""Remaining-syllabus recalculation: pure function tests (done/taught preserved, equal weights, largest remainder, Core-first shortage)."""
from backend.app.services import annual_allocation as alloc
from backend.app.services import recalculation as rc


def t(key, cls="mixed", core=3, non=1, coverage="not_done", taught=0, independent=0):
    return {"topic_key": key, "classification": cls, "core": core, "non_core": non, "independent": independent, "teaching_mode": "INDEPENDENT",
            "coverage": coverage, "taught": taught, "section": key}


def alloc_of(res, key):
    r = next(x for x in res["rows"] if x["topic_key"] == key)
    return r["new_core"] + r["new_non_core"]


def test_all_untaught_equal_weights_sum_to_capacity_exactly_with_largest_remainder():
    topics = [t(f"t{i}") for i in range(5)]
    res = rc.compute(topics, 23)  # 23 over 5 = 5,5,5,4,4 (ties to the earlier topic)
    assert [alloc_of(res, f"t{i}") for i in range(5)] == [5, 5, 5, 4, 4] and sum(alloc_of(res, f"t{i}") for i in range(5)) == 23
    assert res["fits"] and res["core_shortfall"] == 0 and res["total_shortfall"] == 0


def test_done_topics_keep_their_allocation_and_are_not_allocated_again():
    topics = [t("a", coverage="done", core=4, non=0), t("b"), t("c")]
    res = rc.compute(topics, 20)  # done 4 stays; remaining 16 over 2 open topics
    assert alloc_of(res, "a") == 4 and next(r for r in res["rows"] if r["topic_key"] == "a")["changed"] is False
    assert alloc_of(res, "b") + alloc_of(res, "c") == 16 and res["done_topics"] == 1 and res["pool"] == 16


def test_taught_periods_are_a_floor_and_classification_is_preserved():
    topics = [t("a", cls="core", core=4, non=0, coverage="in_progress", taught=3), t("b", cls="non_core", core=0, non=4), t("c")]
    res = rc.compute(topics, 15)  # floors 3; pool 12 over 3 open topics = 4 each
    a = next(r for r in res["rows"] if r["topic_key"] == "a")
    assert a["new_core"] == 3 + 4 and a["new_non_core"] == 0  # core stays core; allocation = taught + share
    assert next(r for r in res["rows"] if r["topic_key"] == "b")["new_core"] == 0  # Non-Core stays Non-Core
    c = next(r for r in res["rows"] if r["topic_key"] == "c")
    assert (c["new_core"], c["new_non_core"]) == (3, 1) and a["remaining_core"] == 4  # mixed splits 2:1, remaining excludes taught


def test_remaining_window_capacity_limits_the_pool():
    topics = [t(f"t{i}") for i in range(4)]
    res = rc.compute(topics, 100, remaining_capacity=12)  # only 12 periods are still left to teach
    assert sum(alloc_of(res, f"t{i}") for i in range(4)) == 12 and res["pool"] == 12


def test_shortage_serves_core_first_then_mixed_then_non_core_and_reports_it():
    topics = [t("nc", cls="non_core", core=0, non=4), t("m1"), t("c1", cls="core", core=4, non=0), t("m2"), t("c2", cls="core", core=4, non=0)]
    res = rc.compute(topics, 3)  # 3 periods for 5 open topics: Core topics first (c1, c2), then the first mixed (m1)
    assert alloc_of(res, "c1") == 1 and alloc_of(res, "c2") == 1 and alloc_of(res, "m1") == 1
    assert alloc_of(res, "nc") == 0 and alloc_of(res, "m2") == 0
    assert res["fits"] is False and res["core_shortfall"] == 1 and res["total_shortfall"] == 2  # m2 has no Core; nc and m2 have nothing
    core_total = sum(r["new_core"] for r in res["rows"])
    assert core_total == 3  # nothing was downgraded to Non-Core to make room


def test_overcommitted_done_work_reports_a_negative_pool_as_shortfall():
    topics = [t("a", coverage="done", core=10, non=0), t("b")]
    res = rc.compute(topics, 8)
    assert res["pool"] == -2 and res["fits"] is False and res["total_shortfall"] >= 2 and alloc_of(res, "a") == 10


def test_holiday_removes_remaining_capacity_and_removal_restores_it():
    cfg = {"start": "2026-04-01", "end": "2026-04-30", "weekdays": [1, 2, 3, 4, 5], "entries": [], "subjectPeriodsPerDay": {"Mathematics": 2, "Science": 2}}
    base = alloc.remaining_periods(cfg, "Mathematics", "2026-04-10")  # days after 10 Apr: 13..30 -> 14 weekdays -> 28 periods
    assert base == 28
    holiday = {**cfg, "entries": [{"id": "h", "type": "HOLIDAY", "label": "x", "start": "2026-04-20", "end": "2026-04-22"}]}
    assert alloc.remaining_periods(holiday, "Mathematics", "2026-04-10") == 28 - 6
    assert alloc.remaining_periods(cfg, "Mathematics", "2026-04-10") == base  # removal restores exactly
    assert alloc.reserve_periods(28) == 3 and alloc.capacity(28)["topic_capacity"] == 25


def locked(key, cls, core, non, **kw):
    return {**t(key, cls=cls, core=core, non=non, **kw), "origin": "teacher"}


def test_teacher_set_classification_and_periods_survive_any_calendar_change():
    topics = [locked("m", "mixed", 3, 1), locked("c", "core", 4, 0), locked("n", "non_core", 0, 4), t("a"), t("b")]
    for cap in (60, 30, 17, 11, 9, 8, 3, 0):  # holidays added (capacity down) and removed (capacity up), repeatedly
        res = rc.compute(topics, 100, remaining_capacity=cap)
        rows = {r["topic_key"]: r for r in res["rows"]}
        assert (rows["m"]["new_core"], rows["m"]["new_non_core"], rows["m"]["classification"]) == (3, 1, "mixed") and not rows["m"]["changed"]
        assert (rows["c"]["new_core"], rows["c"]["new_non_core"], rows["c"]["classification"]) == (4, 0, "core") and not rows["c"]["changed"]
        assert (rows["n"]["new_core"], rows["n"]["new_non_core"], rows["n"]["classification"]) == (0, 4, "non_core") and not rows["n"]["changed"]
    again = rc.compute(topics, 100, remaining_capacity=60)
    assert {r["topic_key"] for r in again["rows"] if r["changed"]} <= {"a", "b"}  # only auto-derived defaults ever change


def test_locked_requirements_are_subtracted_first_and_overcommitment_is_reported_not_trimmed():
    topics = [locked("m", "mixed", 3, 1), t("a"), t("b")]
    res = rc.compute(topics, 100, remaining_capacity=12)  # 4 locked -> 8 left for 2 auto topics = 4 each
    assert alloc_of(res, "a") + alloc_of(res, "b") == 8 and alloc_of(res, "m") == 4 and res["locked_remaining_periods"] == 4
    short = rc.compute(topics, 100, remaining_capacity=3)  # the teacher's own 4 periods already exceed the 3 left
    assert alloc_of(short, "m") == 4 and short["overcommitted_periods"] == 1 and short["fits"] is False and short["total_shortfall"] >= 1


def test_taught_periods_of_a_locked_topic_reduce_what_remains_to_teach_without_changing_the_requirement():
    topics = [locked("m", "mixed", 3, 1, coverage="in_progress", taught=2), t("a")]
    res = rc.compute(topics, 100, remaining_capacity=10)  # locked still needs 2 -> 8 for the auto topic
    m = next(r for r in res["rows"] if r["topic_key"] == "m")
    assert (m["new_core"], m["new_non_core"], m["remaining_core"], m["remaining_non_core"]) == (3, 1, 1, 1) and alloc_of(res, "a") == 8


def test_a_mixed_topic_always_keeps_a_non_core_period_when_it_has_two_or_more():
    assert alloc.split_core_noncore(2, "mixed") == {"core": 1, "non_core": 1}
    assert alloc.split_core_noncore(3, "mixed") == {"core": 2, "non_core": 1}
    assert alloc.split_core_noncore(4, "mixed") == {"core": 3, "non_core": 1}
    assert alloc.split_core_noncore(5, "mixed") == {"core": 4, "non_core": 1}
    assert alloc.split_core_noncore(1, "mixed") == {"core": 1, "non_core": 0}  # one period cannot be both
    assert alloc.split_core_noncore(0, "mixed") == {"core": 0, "non_core": 0}
