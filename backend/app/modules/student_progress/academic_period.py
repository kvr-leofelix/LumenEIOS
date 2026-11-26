"""School-aware academic year, month keys, and term checkpoints.

Defaults assume an Indian CBSE-style June–May year. Schools may override term
month maps via an optional calendar config dict — never hardcode one school's
dates as universal truth inside scoring.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

# Academic year months in instructional order (June → May).
ACADEMIC_MONTH_ORDER: Tuple[int, ...] = (6, 7, 8, 9, 10, 11, 12, 1, 2, 3, 4, 5)

DEFAULT_TERM_MONTHS: Dict[str, Tuple[int, ...]] = {
    "T1": (6, 7, 8, 9),
    "T2": (10, 11, 12),
    "T3": (1, 2, 3),
    "T4": (4, 5),
}

DEFAULT_TERM_LABELS: Dict[str, str] = {
    "T1": "Term 1 (Jun–Sep)",
    "T2": "Term 2 (Oct–Dec)",
    "T3": "Term 3 (Jan–Mar)",
    "T4": "Term 4 (Apr–May)",
}


@dataclass(frozen=True)
class AcademicCalendarConfig:
    """Resolved calendar for one school + academic year label."""

    academic_year: str  # e.g. "2026-2027"
    start_year: int  # calendar year of June start
    term_months: Mapping[str, Sequence[int]]
    term_labels: Mapping[str, str]

    @property
    def end_year(self) -> int:
        return self.start_year + 1


def parse_academic_year_label(label: Optional[str], fallback_start: Optional[int] = None) -> Tuple[str, int]:
    """Parse '2026-2027' → ('2026-2027', 2026)."""
    text = (label or "").strip()
    if len(text) >= 9 and text[4] == "-":
        try:
            start = int(text[0:4])
            end = int(text[5:9])
            if end == start + 1:
                return f"{start}-{end}", start
        except ValueError:
            pass
    start = fallback_start or date.today().year
    # If today is Jan–May, academic year started previous calendar year.
    if fallback_start is None and date.today().month < 6:
        start = date.today().year - 1
    return f"{start}-{start + 1}", start


def resolve_calendar(
    academic_year_label: Optional[str],
    *,
    term_months: Optional[Mapping[str, Sequence[int]]] = None,
    term_labels: Optional[Mapping[str, str]] = None,
    reference: Optional[date] = None,
) -> AcademicCalendarConfig:
    ref = reference or date.today()
    fallback = ref.year if ref.month >= 6 else ref.year - 1
    year_label, start_year = parse_academic_year_label(academic_year_label, fallback)
    return AcademicCalendarConfig(
        academic_year=year_label,
        start_year=start_year,
        term_months=dict(term_months or DEFAULT_TERM_MONTHS),
        term_labels=dict(term_labels or DEFAULT_TERM_LABELS),
    )


def month_key_for(dt: date, calendar: AcademicCalendarConfig) -> Optional[str]:
    """Return YYYY-MM if the date falls inside the academic year window."""
    y, m = dt.year, dt.month
    if m >= 6:
        if y != calendar.start_year:
            return None
    else:
        if y != calendar.end_year:
            return None
    return f"{y:04d}-{m:02d}"


def term_id_for_month(month: int, calendar: AcademicCalendarConfig) -> Optional[str]:
    for term_id, months in calendar.term_months.items():
        if month in months:
            return term_id
    return None


def academic_month_keys(calendar: AcademicCalendarConfig) -> List[str]:
    keys: List[str] = []
    for month in ACADEMIC_MONTH_ORDER:
        year = calendar.start_year if month >= 6 else calendar.end_year
        keys.append(f"{year:04d}-{month:02d}")
    return keys


def coerce_date(value: Optional[object]) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        try:
            return date(int(text[0:4]), int(text[5:7]), int(text[8:10]))
        except ValueError:
            return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None
