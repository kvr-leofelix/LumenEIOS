"""Remaining-syllabus recalculation when the academic calendar changes (the single source for preview AND save).

Classification, required, scheduled and taught are four different things. A teacher's persisted decision (origin 'teacher' or
'approved_import': classification AND required periods) is NEVER rewritten by a calendar change; only auto-derived defaults
(origin 'demo_default') are recalculated. Locked requirements are subtracted from the capacity first; if they alone exceed the time left,
the overcommitment is reported as a shortfall, not silently trimmed.

Definitions (integers only, deterministic, no clock, no randomness):
  P = available subject periods on instructional days of the whole academic year (annual, not just the remainder)
  R = ceil(0.10 * P)         reserve
  T = P - R                  planned topic allocation capacity
  Done topic                 coverage == done. Its saved allocation is history and is NEVER changed; it counts against T.
  Open topic                 anything else (not done / in progress).
  floor_i                    periods already actually TAUGHT in an open topic (execution records TAUGHT/PARTIAL, not superseded).
                             An open topic is never allocated fewer periods than were already taught.
  T_rem                      topic capacity of the REMAINING window only: periods on instructional days after the planning date,
                             minus their own 10% reserve. Days already gone cannot be taught again, so they are not capacity.
  pool                       min(T_rem, T - sum(done allocations) - sum(floor_i)): remaining capacity for work not yet taught,
                             never allowing the plan's total to exceed the annual topic capacity T
  share_i                    equal weights W_i = 1 over the open topics, integer largest-remainder: sum(share_i) == pool exactly
  allocation_i               floor_i + share_i, then split by the topic's PERSISTED classification:
                             core -> all Core, non_core -> all Non-Core, mixed -> 2:1 (Core rounded up).

Shortage (pool < number of open topics): every open topic needs at least one period, and Core must not be silently dropped, so the
pool is handed out one period at a time to Core topics first, then Mixed, then Non-Core, in syllabus order. Anything that cannot be
placed is reported, never hidden:
  core_shortfall   = number of open Core/Mixed topics that end with zero Core periods
  total_shortfall  = open topics that end with zero periods in total + any negative pool (periods over-committed to done/taught work)
Required, scheduled and taught are kept apart: this module only decides REQUIRED periods; scheduling is done by the planner and
taught periods come from classroom execution records.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence

from backend.app.services import annual_allocation as alloc

CLASS_RANK = {"core": 0, "mixed": 1, "non_core": 2}


def is_locked(t: Dict[str, Any]) -> bool:
    """A topic whose requirement is a teacher's persisted decision (origin 'teacher' / 'approved_import'): a calendar change never rewrites
    its classification OR its required periods. Only auto-derived defaults (origin 'demo_default') are recalculated."""
    return t.get("origin", "demo_default") != "demo_default"


def compute(topics: Sequence[Dict[str, Any]], topic_capacity: int, remaining_capacity: Optional[int] = None) -> Dict[str, Any]:
    """topics: ordered dicts with topic_key, classification, core, non_core, independent, teaching_mode, coverage, taught, origin."""
    done = [t for t in topics if t["coverage"] == "done"]
    open_topics = [t for t in topics if t["coverage"] != "done"]
    locked = [t for t in open_topics if is_locked(t)]
    auto = [t for t in open_topics if not is_locked(t)]
    fixed = sum(t["core"] + t["non_core"] for t in done)
    locked_total = sum(t["core"] + t["non_core"] for t in locked)
    locked_remaining = sum(max(0, t["core"] + t["non_core"] - t.get("taught", 0)) for t in locked)
    floors = {t["topic_key"]: t.get("taught", 0) for t in auto}
    floor_total = sum(floors.values())
    annual_room = topic_capacity - fixed - locked_total - floor_total
    window_room = annual_room if remaining_capacity is None else remaining_capacity - locked_remaining
    pool = min(window_room, annual_room)
    shares: Dict[str, int] = {t["topic_key"]: 0 for t in auto}
    if auto and pool > 0:
        if pool >= len(auto):
            for t, s in zip(auto, alloc.largest_remainder(pool, [1] * len(auto))):
                shares[t["topic_key"]] = s
        else:  # shortage: Core first, then Mixed, then Non-Core; each served topic gets one period
            order = sorted(range(len(auto)), key=lambda i: (CLASS_RANK.get(auto[i]["classification"], 3), i))
            for i in order[:pool]:
                shares[auto[i]["topic_key"]] = 1
    rows: List[Dict[str, Any]] = []
    for t in topics:
        k = t["topic_key"]
        if t["coverage"] == "done":
            rows.append({**t, "new_core": t["core"], "new_non_core": t["non_core"], "new_independent": t["independent"], "changed": False,
                         "remaining_core": 0, "remaining_non_core": 0, "state": "done", "locked": False})
            continue
        if is_locked(t):  # the teacher's classification and required periods are kept exactly
            total = t["core"] + t["non_core"]
            taught = min(t.get("taught", 0), total)
            rows.append({**t, "new_core": t["core"], "new_non_core": t["non_core"], "new_independent": t["independent"], "changed": False,
                         "remaining_core": max(0, t["core"] - min(taught, t["core"])), "remaining_non_core": max(0, t["non_core"] - max(0, taught - t["core"])),
                         "state": "partial" if taught else "untaught", "locked": True})
            continue
        total = floors[k] + shares[k]
        split = alloc.split_core_noncore(total, t["classification"])
        independent = min(t["independent"], split["non_core"])
        taught = min(t.get("taught", 0), total)
        rows.append({**t, "new_core": split["core"], "new_non_core": split["non_core"], "new_independent": independent,
                     "changed": (split["core"], split["non_core"], independent) != (t["core"], t["non_core"], t["independent"]),
                     "remaining_core": max(0, split["core"] - min(taught, split["core"])), "remaining_non_core": max(0, split["non_core"] - max(0, taught - split["core"])),
                     "state": "partial" if taught else "untaught", "locked": False})
    core_short = sum(1 for r in rows if r["state"] != "done" and not r["locked"] and r["classification"] in ("core", "mixed") and r["new_core"] == 0)
    zero = sum(1 for r in rows if r["state"] != "done" and not r["locked"] and r["new_core"] + r["new_non_core"] == 0)
    overcommitted = max(0, -pool)  # periods the teacher-set requirements (plus done/taught work) exceed the available time by
    return {"rows": rows, "pool": pool, "annual_room": annual_room, "remaining_capacity": remaining_capacity, "fixed_done_periods": fixed,
            "taught_floor_periods": floor_total, "open_topics": len(open_topics), "done_topics": len(done), "locked_topics": len(locked),
            "locked_remaining_periods": locked_remaining, "overcommitted_periods": overcommitted,
            "core_shortfall": core_short, "total_shortfall": zero + overcommitted,
            "fits": core_short == 0 and zero == 0 and pool >= 0,
            "before": {"core": sum(t["core"] for t in topics), "non_core": sum(t["non_core"] for t in topics)},
            "after": {"core": sum(r["new_core"] for r in rows), "non_core": sum(r["new_non_core"] for r in rows)}}
