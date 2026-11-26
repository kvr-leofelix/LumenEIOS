"""Deterministic annual period allocation (backend source of truth).

P = scheduled subject periods on eligible instructional days (from the academic calendar and timetable)
R = ceil(0.10 * P) reserved for revision, assessment and disruption
T = P - R allocated to syllabus topics by equal weight (largest-remainder rounding)

Pure functions: no database, no randomness, no clock. The calendar config mirrors the frontend
`AcademicConfig` shape so the existing Academic Configuration screen remains the editing surface.
"""
from __future__ import annotations

import hashlib
import math
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Sequence

RESERVE_FRACTION_NUM = 1  # 10% expressed as an exact integer ratio to avoid float error
RESERVE_FRACTION_DEN = 10
REMOVES_WORKING_DAY = {"HOLIDAY": True, "VACATION": True, "EXAM": False, "EVENT": False}
MAX_DAYS = 800


class AllocationError(ValueError):
    pass


def _parse(d: str) -> date:
    try:
        return date.fromisoformat(d)
    except (TypeError, ValueError) as exc:
        raise AllocationError(f"Invalid date: {d!r}") from exc


def dates_between(start: str, end: str) -> List[str]:
    s, e = _parse(start), _parse(end)
    if s > e:
        return []
    out: List[str] = []
    cur = s
    while cur <= e and len(out) < MAX_DAYS:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def instructional_dates(config: dict, apply_horizon: bool = True) -> List[str]:
    """Working weekday inside the year that is not a holiday/vacation (school closed) or exam/event
    (school open, no teaching). Weekdays use 0 = Sunday ... 6 = Saturday, as in the frontend."""
    weekdays = set(config.get("weekdays", [1, 2, 3, 4, 5]))
    blocked: set = set()
    for entry in config.get("entries", []):
        blocked.update(dates_between(entry["start"], entry["end"]))
    out = []
    for iso in dates_between(config["start"], config["end"]):
        js_weekday = (date.fromisoformat(iso).weekday() + 1) % 7  # Monday=0 -> 1 ... Sunday=6 -> 0
        if js_weekday in weekdays and iso not in blocked:
            out.append(iso)
    horizon = config.get("horizonDays") if apply_horizon else None
    return out[:horizon] if horizon else out


def subject_periods_for_date(config: dict, subject: str, iso: str) -> int:
    """Timetable periods for `subject` on a date. Supports an optional per-weekday override
    `subjectPeriodsByWeekday[subject][js_weekday]` on top of the flat `subjectPeriodsPerDay`."""
    by_weekday = (config.get("subjectPeriodsByWeekday") or {}).get(subject)
    if by_weekday:
        js_weekday = (date.fromisoformat(iso).weekday() + 1) % 7
        return int(by_weekday.get(str(js_weekday), by_weekday.get(js_weekday, 0)) or 0)
    return int((config.get("subjectPeriodsPerDay") or {}).get(subject, 0) or 0)


def available_periods(config: dict, subject: str) -> int:
    # Annual allocations use the complete versioned academic calendar. `horizonDays` is
    # only a display/scheduling horizon and must never shrink the annual topic budget.
    return sum(subject_periods_for_date(config, subject, d) for d in instructional_dates(config, apply_horizon=False))


def remaining_periods(config: dict, subject: str, after: str) -> int:
    """Subject periods on instructional days STRICTLY AFTER `after` (the planning date). Days already gone are not capacity."""
    return sum(subject_periods_for_date(config, subject, d) for d in instructional_dates(config, apply_horizon=False) if d > after)


def remaining_days(config: dict, after: str) -> int:
    return sum(1 for d in instructional_dates(config, apply_horizon=False) if d > after)


def reserve_periods(p: int) -> int:
    """R = ceil(0.10 * P), computed with integers."""
    if p < 0:
        raise AllocationError("Available periods cannot be negative.")
    return -(-p * RESERVE_FRACTION_NUM // RESERVE_FRACTION_DEN)


def capacity(p: int) -> Dict[str, int]:
    r = reserve_periods(p)
    return {"available_periods": p, "reserved_periods": r, "topic_capacity": p - r}


def largest_remainder(total: int, weights: Sequence[int]) -> List[int]:
    """Distribute `total` over `weights` so the integer parts sum exactly to `total`.
    Ties on the fractional remainder resolve to the earlier syllabus position."""
    if total < 0:
        raise AllocationError("Total must be non-negative.")
    if not weights:
        return []
    if any(w < 0 for w in weights) or sum(weights) == 0:
        raise AllocationError("Weights must be non-negative with a positive sum.")
    wsum = sum(weights)
    floors = [total * w // wsum for w in weights]
    remainders = [(total * w) % wsum for w in weights]  # exact integer fractional parts
    leftover = total - sum(floors)
    order = sorted(range(len(weights)), key=lambda i: (-remainders[i], i))
    for i in order[:leftover]:
        floors[i] += 1
    return floors


def split_core_noncore(allocation: int, classification: str) -> Dict[str, int]:
    """Core-only -> all Core; Non-Core-only -> all Non-Core; mixed -> 2:1 Core:Non-Core.
    Odd remainders round Core up (deterministic), so core + non_core == allocation. A mixed topic with 2 or more periods
    always keeps at least one Non-Core period (the label would otherwise be untrue)."""
    if classification == "core":
        return {"core": allocation, "non_core": 0}
    if classification == "non_core":
        return {"core": 0, "non_core": allocation}
    if classification == "mixed":
        core = -(-allocation * 2 // 3)  # ceil(2/3 * allocation)
        if allocation >= 2:
            core = min(core, allocation - 1)  # a Mixed topic always keeps at least one Non-Core period (2 -> 1 + 1, never 2 + 0)
        return {"core": core, "non_core": allocation - core}
    raise AllocationError(f"Unknown classification {classification!r}")


def demo_classification(topic_key: str) -> str:
    """Hypothetical demonstration pattern. A pure function of the topic key only, so every school
    and every refresh gets the same result. NOT official NCERT or expert-approved."""
    bucket = int(hashlib.sha256(topic_key.encode("utf-8")).hexdigest(), 16) % 6
    return ("core", "core", "mixed", "mixed", "mixed", "non_core")[bucket]


def demo_teaching_mode(topic_key: str) -> str:
    """Stable hypothetical mode; sharing is only executed when an approved lead relationship exists."""
    bucket = int(hashlib.sha256(("teaching-mode:" + topic_key).encode("utf-8")).hexdigest(), 16) % 3
    return "SHARED" if bucket == 0 else "INDEPENDENT"


def topic_allocations(topics: Sequence[dict], p: int, topic_capacity_override: Optional[int] = None) -> List[Dict]:
    """Allocate T over existing topic weights and configured classes; independent is Non-Core subset.

    Each input has topic_key, optional classification, weight, and teaching_mode. Missing/invalid weights
    fall back to 1. Core/Non-Core/Mixed classification is never changed by a capacity recalculation.
    """
    t = capacity(p)["topic_capacity"] if topic_capacity_override is None else topic_capacity_override
    if t < 0:
        raise AllocationError("Topic capacity cannot be negative.")
    if not topics:
        return []
    weights = [int(x.get("weight", 1)) if isinstance(x.get("weight", 1), int) and x.get("weight", 1) > 0 else 1 for x in topics]
    shares = largest_remainder(t, weights)
    rows = []
    for topic, share in zip(topics, shares):
        key = str(topic["topic_key"])
        classification = topic.get("classification") or demo_classification(key)
        mode = topic.get("teaching_mode") or demo_teaching_mode(key)
        split = split_core_noncore(share, classification)
        # Independent study is explicitly carved out of Non-Core, never counted as classroom time.
        independent = split["non_core"] // 2 if mode == "INDEPENDENT" else 0
        rows.append({"topic_key": key, "classification": classification, "allocation": share,
                     "core": split["core"], "non_core": split["non_core"],
                     "teaching_mode": mode, "independent_periods": independent,
                     "classroom_periods": share - independent})
    return rows


def default_allocations(topic_keys: Sequence[str], p: int) -> List[Dict]:
    """Equal-weight defaults for topics given in syllabus order."""
    return topic_allocations([{"topic_key": k, "weight": 1} for k in topic_keys], p)


def validate_requirements(rows: Iterable[dict], topic_capacity: int) -> Dict:
    """Capacity check used by the save endpoint. Returns totals and, when invalid, reasons."""
    rows = list(rows)
    errors: List[str] = []
    total = 0
    for row in rows:
        core, non_core = row.get("core_periods"), row.get("non_core_periods")
        if not isinstance(core, int) or not isinstance(non_core, int) or isinstance(core, bool) or isinstance(non_core, bool):
            errors.append(f"{row.get('topic_key')}: period counts must be whole numbers.")
            continue
        if core < 0 or non_core < 0:
            errors.append(f"{row.get('topic_key')}: period counts cannot be negative.")
            continue
        total += core + non_core
    remaining = topic_capacity - total
    if remaining < 0:
        errors.append(
            f"Requirements total {total} periods but only {topic_capacity} are available after the 10% reserve "
            f"(deficit {-remaining})."
        )
    return {"proposed_total": total, "topic_capacity": topic_capacity, "remaining": remaining,
            "deficit": max(0, -remaining), "valid": not errors, "errors": errors}


def lost_summary(records: Iterable[dict]) -> Dict[str, int]:
    """Lost days = distinct calendar dates; lost periods = distinct (date, period) records."""
    periods = {(r["date"], r["period"]) for r in records}
    return {"lost_days": len({d for d, _ in periods}), "lost_periods": len(periods)}


def day_counts(config: dict, today: Optional[str], lost_dates: Iterable[str]) -> Dict[str, int]:
    """Teaching-day progress for the Time-Aware page. Days lost are not counted as completed."""
    days = instructional_dates(config)
    lost = {d for d in lost_dates if d in set(days)}
    completed = [d for d in days if today and d <= today and d not in lost]
    remaining = [d for d in days if not today or d > today]
    return {"total_days": len(days), "completed_days": len(completed), "remaining_days": len(remaining),
            "lost_days": len(lost)}
