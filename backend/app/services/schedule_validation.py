"""Structural validation of a persisted schedule (a plan's version or a recovery proposal), whoever generated it.

Calendar membership and period-range checks only: the server never allocates periods. Used by the relational plan service for every
draft, proposal and approved version, and by the one-time workspace import. (Moved out of planning_workspace_service so relational
code no longer depends on the legacy workspace document.)
"""
from datetime import date, timedelta
from typing import Any, Dict, List, Optional


def _teaching_dates(config: Any) -> Optional[set]:
    """Planning (instructional) dates of an Academic Configuration: working weekday, not covered by any
    holiday/vacation/exam/event entry, truncated to the horizon. Mirrors src/lib/planning/calendar.ts summarizeCalendar.
    This is a calendar membership check only; the server never allocates periods."""
    try:
        start, end = date.fromisoformat(config["start"]), date.fromisoformat(config["end"])
        weekdays = set(config["weekdays"])
        blocked = set()
        for e in config.get("entries", []):
            d, last = date.fromisoformat(e["start"]), date.fromisoformat(e["end"])
            while d <= last:
                blocked.add(d)
                d += timedelta(days=1)
        out, d = [], start
        while d <= end:
            if (d.weekday() + 1) % 7 in weekdays and d not in blocked:
                out.append(d.isoformat())
            d += timedelta(days=1)
        horizon = config.get("horizonDays")
        return set(out if horizon is None else out[: int(horizon)])
    except (KeyError, TypeError, ValueError):
        return None


def validate_schedule(lessons: Any, config: Any, subject: Any, previous: Optional[List[Dict[str, Any]]], label: str) -> List[str]:
    """Structural invariants every persisted schedule version / proposal must satisfy, whoever generated it."""
    v: List[str] = []
    if not isinstance(lessons, list) or not isinstance(config, dict):
        return [f"{label}: malformed schedule."]
    teaching = _teaching_dates(config)
    if teaching is None:
        return [f"{label}: its Academic Configuration is malformed."]
    per_day = (config.get("subjectPeriodsPerDay") or {}).get(subject)
    seen: Dict[Any, str] = {}
    node_ids = set()
    for lesson in lessons:
        if not isinstance(lesson, dict):
            v.append(f"{label}: malformed lesson.")
            continue
        node = str(lesson.get("nodeId"))
        node_ids.add(node)
        core, non_core = lesson.get("corePeriods"), lesson.get("nonCorePeriods")
        if core is not None and non_core is not None and lesson.get("requiredPeriods") != core + non_core:
            v.append(f"{label}: {node} requirement does not equal its approved Core + Non-Core periods.")
        for slot in lesson.get("slots") or []:
            key = (slot.get("date"), slot.get("period"))
            if slot.get("date") not in teaching:
                v.append(f"{label}: {node} is placed on {slot.get('date')}, which is not a teaching date in the configured calendar.")
            if not isinstance(slot.get("period"), int) or slot["period"] < 1 or (per_day is not None and slot["period"] > per_day):
                v.append(f"{label}: {node} uses period {slot.get('period')}, outside the subject's configured periods.")
            if key in seen:
                v.append(f"{label}: period {key[1]} on {key[0]} is allocated to both {seen[key]} and {node}.")
            seen[key] = node
    if previous is not None:
        before = {str(x.get("nodeId")): x for x in previous if isinstance(x, dict)}
        for node, old in before.items():
            if node not in node_ids:
                v.append(f"{label}: topic {node} was silently dropped from the schedule.")
        for lesson in lessons:
            old = before.get(str(lesson.get("nodeId"))) if isinstance(lesson, dict) else None
            if old and old.get("corePeriods") is not None and (lesson.get("corePeriods") or 0) < old["corePeriods"]:
                v.append(f"{label}: approved Core requirement of {lesson.get('nodeId')} was reduced.")
        # Core conservation: every Core period of the previous schedule must still be either placed in a Core slot or explicitly
        # reported as unscheduled Core. A client can no longer keep the declared `corePeriods` while flipping Core slots to Non-Core.
        def core_accounted(items: Any) -> int:
            total = 0
            for x in items:
                if isinstance(x, dict):
                    total += sum(1 for sl in (x.get("slots") or []) if isinstance(sl, dict) and sl.get("kind") == "CORE")
                    total += int(x.get("coreUnscheduled") or 0)
            return total
        if core_accounted(lessons) < core_accounted(previous):
            v.append(f"{label}: Core periods were silently reduced ({core_accounted(lessons)} accounted for, {core_accounted(previous)} before); "
                     "a Core period must stay scheduled or be reported as unresolved.")
    return v
