"""One calendar for every role, assembled at read time from records that already exist.

Sources (nothing is copied, so Academic Config stays the single source of truth):
  * the school's latest Academic Config calendar: holidays, vacations, exam windows, events, session start/end
  * lost teaching days: dates with lost periods recorded in the Time-Aware Engine
  * assessments (class tests / exams) for the classes the user teaches, attends or is the parent of
  * differentiated-homework deadlines (due_at)
  * announcements the user was sent that carry an event date (read-only; never written into Academic Config)
  * the user's own tasks and deadlines (the only table this feature owns)

Visibility is scoped by role on the server; the browser never decides what a user may see.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Set

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import user_school_ids
from backend.app.services import announcement_service as announcements
from backend.app.models.calendar_events import PersonalCalendarEvent
from backend.app.models.entities import (
    Assessment, ClassSection, ParentStudentLink, School, Student, Subject, TeacherAssignment, User,
)
from backend.app.models.teacher_planning import SchoolPlanCalendar
from backend.app.modules.differentiated_homework.models import HomeworkAssignmentRecord
from backend.app.modules.differentiated_homework.student_access import resolve_linked_student

MAX_RANGE_DAYS = 400
CATEGORIES = ("holiday", "vacation", "exam", "event", "session", "deadline", "lost", "personal", "announcement")
_ENTRY_CATEGORY = {"HOLIDAY": "holiday", "VACATION": "vacation", "EXAM": "exam", "EVENT": "event"}


def parse_day(value: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _event(id: str, category: str, title: str, start: date, end: Optional[date] = None, *, source: str,
           detail: str = "", editable: bool = False, **extra: Any) -> Dict[str, Any]:
    end = end or start
    if end < start:
        end = start
    return {"id": id, "category": category, "title": title, "start": start.isoformat(), "end": end.isoformat(),
            "source": source, "detail": detail, "editable": editable, **extra}


def _overlaps(start: date, end: date, lo: date, hi: date) -> bool:
    return start <= hi and end >= lo


class Scope:
    """Who the user is allowed to see, resolved once per request."""

    def __init__(self) -> None:
        self.school_ids: Set[str] = set()
        self.class_ids: Set[str] = set()
        self.student_ids: Set[str] = set()
        self.students: Dict[str, Student] = {}


async def resolve_scope(db: AsyncSession, user: User, school_id: Optional[str]) -> Scope:
    scope = Scope()
    if user.role == "student":
        student = await resolve_linked_student(db, user)
        if student:
            scope.school_ids, scope.class_ids = {student.school_id}, {student.class_id}
            scope.student_ids, scope.students = {student.id}, {student.id: student}
        return scope
    if user.role == "parent":
        children = list((await db.scalars(
            select(Student).where(Student.id.in_(
                select(ParentStudentLink.student_id).where(ParentStudentLink.parent_user_id == user.id))))).all())
        scope.students = {c.id: c for c in children}
        scope.student_ids = set(scope.students)
        scope.school_ids = {c.school_id for c in children}
        scope.class_ids = {c.class_id for c in children}
        return scope
    if user.role == "admin":
        chosen = school_id or user.school_id
        scope.school_ids = {chosen} if chosen else set()
    else:
        allowed = await user_school_ids(db, user)
        scope.school_ids = ({school_id} & allowed) if school_id and school_id in allowed else allowed
    if not scope.school_ids:
        return scope
    classes = select(ClassSection.id).where(ClassSection.school_id.in_(scope.school_ids))
    if user.role == "teacher":
        taught = select(TeacherAssignment.class_id).where(TeacherAssignment.teacher_id == user.id)
        classes = classes.where(or_(ClassSection.class_teacher_id == user.id, ClassSection.id.in_(taught)))
    scope.class_ids = set((await db.scalars(classes)).all())
    return scope


async def _school_calendar_events(db: AsyncSession, scope: Scope, lo: date, hi: date):
    events: List[Dict[str, Any]] = []
    meta: Dict[str, Any] = {"schools": [], "session_start": None, "session_end": None, "working_weekdays": [1, 2, 3, 4, 5]}
    if not scope.school_ids:
        return events, meta
    names = {s.id: s.name for s in (await db.scalars(select(School).where(School.id.in_(scope.school_ids)))).all()}
    meta["schools"] = [{"id": sid, "name": names.get(sid, sid)} for sid in sorted(scope.school_ids)]
    rows = (await db.scalars(select(SchoolPlanCalendar).where(SchoolPlanCalendar.school_id.in_(scope.school_ids)))).all()
    latest: Dict[tuple, SchoolPlanCalendar] = {}
    for row in rows:  # append-only versions: the highest version per school and year is current
        key = (row.school_id, row.academic_year)
        if key not in latest or row.version > latest[key].version:
            latest[key] = row
    multi = len(scope.school_ids) > 1
    for (sid, _year), row in sorted(latest.items()):
        cfg = row.config or {}
        prefix = f"{names.get(sid, sid)}: " if multi else ""
        start, end = parse_day(cfg.get("start")), parse_day(cfg.get("end"))
        if start and end and _overlaps(start, end, lo, hi):
            meta["session_start"] = meta["session_start"] or start.isoformat()
            meta["session_end"] = meta["session_end"] or end.isoformat()
            if isinstance(cfg.get("weekdays"), list):
                meta["working_weekdays"] = [d for d in cfg["weekdays"] if isinstance(d, int)]
            meta["year"] = cfg.get("year") or row.academic_year
        if start and lo <= start <= hi:
            events.append(_event(f"session-start:{sid}:{row.academic_year}", "session", f"{prefix}Academic session begins",
                                 start, source="school", detail=f"Session {cfg.get('year', row.academic_year)}", school_id=sid))
        if end and lo <= end <= hi:
            events.append(_event(f"session-end:{sid}:{row.academic_year}", "session", f"{prefix}Academic session ends",
                                 end, source="school", detail=f"Session {cfg.get('year', row.academic_year)}", school_id=sid))
        for entry in cfg.get("entries") or []:
            if not isinstance(entry, dict):
                continue
            s, e = parse_day(entry.get("start")), parse_day(entry.get("end") or entry.get("start"))
            category = _ENTRY_CATEGORY.get(str(entry.get("type", "")).upper())
            if not (s and e and category and _overlaps(s, e, lo, hi)):
                continue
            label = str(entry.get("label") or category.title()).strip()
            events.append(_event(f"cal:{sid}:{entry.get('id') or label}:{s}", category, f"{prefix}{label}", s, e,
                                 source="school", school_id=sid))
    return events, meta


async def _disruption_events(db: AsyncSession, user: User, scope: Scope, lo: date, hi: date) -> List[Dict[str, Any]]:
    """Lost teaching days: dates with lost periods recorded in the Time-Aware Engine (the same count the dashboards
    and the engine show), not the retired school disruption register. Leadership sees the school; a teacher their own
    losses; a student or parent only losses in their class's grade."""
    if not scope.school_ids:
        return []
    from backend.app.services.lost_period_service import school_lost_days
    filters: Dict[str, Any] = {}
    if user.role == "teacher":
        filters["teacher_id"] = user.id
    elif user.role in ("student", "parent"):
        classes = (await db.scalars(select(ClassSection).where(ClassSection.id.in_(scope.class_ids)))).all()
        filters["grades"] = {c.grade for c in classes}
    out = []
    for day_row in await school_lost_days(db, scope.school_ids, **filters):
        day = parse_day(day_row["date"])
        if day and lo <= day <= hi:
            out.append(_event(f"lost:{day_row['id']}", "lost", f"Teaching disrupted: {day_row['reason']}", day,
                              source="school", detail=day_row["notes"], school_id=day_row["schoolId"]))
    return out


async def _assessment_events(db: AsyncSession, user: User, scope: Scope, lo: date, hi: date) -> List[Dict[str, Any]]:
    if not scope.class_ids:
        return []
    query = select(Assessment).where(Assessment.class_id.in_(scope.class_ids))
    if user.role != "teacher":
        # Drafts are not published to learners or families, and for leadership they are not yet events: the exam
        # window itself comes from Academic Config. Listing every class x subject draft buried the calendar.
        query = query.where(Assessment.status != "draft")
    rows = (await db.scalars(query)).all()
    if user.role == "teacher":
        # A teacher sees the assessments of the subjects they teach in each class (drafts included: their own work),
        # plus published assessments of other subjects in the class they are class teacher of.
        taught = set((await db.execute(select(TeacherAssignment.class_id, TeacherAssignment.subject_id)
                                       .where(TeacherAssignment.teacher_id == user.id))).all())
        homeroom = set((await db.scalars(select(ClassSection.id).where(ClassSection.class_teacher_id == user.id))).all())
        rows = [r for r in rows if (r.class_id, r.subject_id) in taught or (r.class_id in homeroom and r.status != "draft")]
    subjects = {s.id: s.name for s in (await db.scalars(select(Subject))).all()}
    classes = {c.id: c.name for c in (await db.scalars(select(ClassSection).where(ClassSection.id.in_({r.class_id for r in rows})))).all()} if rows else {}
    out = []
    for row in rows:
        day = parse_day(row.date)
        if not day or not lo <= day <= hi:
            continue
        subject = subjects.get(row.subject_id, "")
        detail = " · ".join(x for x in (subject, classes.get(row.class_id, ""), f"{row.duration_minutes} min",
                                        f"{row.total_marks} marks", row.status.title()) if x)
        # Staff see several classes at once, so name the class; a learner or parent only ever sees their own.
        label = classes.get(row.class_id, "").replace("Class ", "")
        # Class first, so the same paper for two classes stays distinguishable when a narrow list truncates it.
        title = f"{label} · {row.title}" if label and user.role in ("teacher", "principal", "admin") else row.title
        out.append(_event(f"assessment:{row.id}", "exam", title, day, source="assessment", detail=detail,
                          school_id=row.school_id, status=row.status))
    return out


async def _homework_events(db: AsyncSession, user: User, scope: Scope, lo: date, hi: date) -> List[Dict[str, Any]]:
    query = select(HomeworkAssignmentRecord).where(HomeworkAssignmentRecord.due_at.is_not(None))
    if user.role in ("student", "parent"):
        if not scope.student_ids:
            return []
        query = query.where(HomeworkAssignmentRecord.student_id.in_(scope.student_ids))
    elif user.role == "teacher":
        query = query.where(HomeworkAssignmentRecord.assigned_by == user.id)
    else:
        return []  # one row per student per assignment: too granular for a school-wide calendar
    subjects = {s.id: s.name for s in (await db.scalars(select(Subject))).all()}
    out = []
    for row in (await db.scalars(query)).all():
        due = row.due_at.date() if isinstance(row.due_at, datetime) else parse_day(row.due_at)
        if not due or not lo <= due <= hi:
            continue
        subject = subjects.get(row.subject_id, "Homework")
        who = scope.students.get(row.student_id) if user.role == "parent" else None
        title = f"Homework due: {subject}" + (f" ({who.name.split()[0]})" if who and who.name else "")
        out.append(_event(f"homework:{row.id}", "deadline", title, due, source="homework",
                          detail=f"Differentiated homework · {row.status}", school_id=row.school_id))
    return out


def personal_to_event(row: PersonalCalendarEvent) -> Dict[str, Any]:
    start = parse_day(row.start_date) or date.today()
    end = parse_day(row.end_date) if row.end_date else None
    return _event(f"me:{row.id}", "personal", row.title, start, end, source="personal", detail=row.notes or "",
                  editable=True, personal_id=row.id, personal_kind=row.kind, done=bool(row.is_done))


async def _personal_events(db: AsyncSession, user: User, lo: date, hi: date) -> List[Dict[str, Any]]:
    rows = (await db.scalars(select(PersonalCalendarEvent).where(PersonalCalendarEvent.user_id == user.id))).all()
    out = []
    for row in rows:
        event = personal_to_event(row)
        if _overlaps(date.fromisoformat(event["start"]), date.fromisoformat(event["end"]), lo, hi):
            out.append(event)
    return out


async def _announcement_events(db: AsyncSession, user: User, scope: Scope, lo: date, hi: date) -> List[Dict[str, Any]]:
    if not scope.school_ids:
        return []
    rows = await announcements.visible_announcements(db, user, set(scope.school_ids), only_events=True)
    out = []
    for ann in rows:
        start, end = parse_day(ann.event_start), parse_day(ann.event_end or ann.event_start)
        if start and end and _overlaps(start, end, lo, hi):
            out.append(announcements.calendar_event(ann))
    return out


async def collect_events(db: AsyncSession, user: User, school_id: Optional[str], lo: date, hi: date) -> Dict[str, Any]:
    if hi < lo:
        raise ValueError("The end date is before the start date.")
    if (hi - lo).days > MAX_RANGE_DAYS:
        raise ValueError(f"Ask for at most {MAX_RANGE_DAYS} days at a time.")
    scope = await resolve_scope(db, user, school_id)
    school_events, meta = await _school_calendar_events(db, scope, lo, hi)
    events = (school_events + await _disruption_events(db, user, scope, lo, hi) + await _assessment_events(db, user, scope, lo, hi)
              + await _homework_events(db, user, scope, lo, hi) + await _announcement_events(db, user, scope, lo, hi)
              + await _personal_events(db, user, lo, hi))
    events.sort(key=lambda e: (e["start"], e["end"], e["category"], e["title"]))
    return {"start": lo.isoformat(), "end": hi.isoformat(), "events": events, "meta": meta}


async def upcoming_for_assistant(db: AsyncSession, user: User, school_id: Optional[str], days: int = 45,
                                 limit: Optional[int] = 60) -> List[Dict[str, Any]]:
    """Compact, read-only view of the next weeks for the assistant (same scoping as the calendar page). `limit` keeps
    the model's prompt small; direct calendar answers pass None so a type is never cut off by earlier items."""
    today = date.today()
    data = await collect_events(db, user, school_id, today, today + timedelta(days=days))
    events = data["events"] if limit is None else data["events"][:limit]
    return [{"date": e["start"] if e["start"] == e["end"] else f"{e['start']} to {e['end']}", "type": e["category"],
             "title": e["title"], "detail": e["detail"]} for e in events]


_HIGHLIGHT_LABELS = {"exam": "next_exam_or_test", "deadline": "next_homework_deadline", "holiday": "next_holiday",
                     "vacation": "next_vacation", "event": "next_school_event", "announcement": "next_announced_event", "personal": "next_personal_task"}


def assistant_highlights(items: List[Dict[str, Any]], today: date) -> Dict[str, Any]:
    """Answers small models get wrong when they must scan a long list: the next item of each kind and the coming week.

    Computed here from the same role-scoped items the assistant already receives, so it adds no new visibility.
    """
    week_end = (today + timedelta(days=7)).isoformat()
    out: Dict[str, Any] = {}
    for item in items:
        key = _HIGHLIGHT_LABELS.get(item["type"])
        if key and key not in out:
            out[key] = f"{item['title']} on {item['date']}"
    out["next_7_days"] = [f"{i['date']}: {i['title']} ({i['type']})" for i in items if i["date"][:10] <= week_end][:15]
    return out


# ---- direct answers to calendar questions (no model) ------------------------------------------------------------------
# "When is my next test?" is a date lookup; the small local model got it wrong (no date, wrong page, "Yes", or claiming
# the data was not visible). Clear calendar questions are answered here from the same role-scoped items instead.
import re as _re

_KINDS = (
    ("holiday", _re.compile(r"\b(holidays?|vacations?|breaks?|school (is )?closed|day off|days off|leave)\b"), ("holiday", "vacation")),
    ("deadline", _re.compile(r"\b(homework|due|deadlines?|assignments?|submit|submission)\b"), ("deadline",)),
    ("exam", _re.compile(r"\b(exams?|tests?|quiz(zes)?|worksheets?|papers?|assessments?|periodic)\b"), ("exam",)),
    ("event", _re.compile(r"\b(events?|functions?|sports day|celebrations?|annual day|meetings?)\b"), ("event",)),
    ("task", _re.compile(r"\b(my tasks?|my reminders?|to-?do)\b"), ("personal",)),
)
_TIMING = _re.compile(r"\b(when|next|upcoming|coming|due|this week|next week|today|tomorrow|schedule|scheduled|calendar|"
                      r"any (exams?|tests?|homework|holidays?|deadlines?)|what'?s on|what is on|date of)\b")
_WEEK = _re.compile(r"\b(this week|next 7 days|coming week|today|tomorrow|what'?s on|what is on)\b")
_PERFORMANCE = _re.compile(r"\b(how did|marks?|scores?|results?|grades?|performance|weak|strong|progress|feedback)\b")
CALENDAR_LOOKAHEAD_DAYS = 180


def calendar_intent(message: str) -> Optional[str]:
    """'holiday' / 'deadline' / 'exam' / 'event' / 'task' / 'week' for a clear calendar question, else None."""
    text = (message or "").lower()
    if not _TIMING.search(text) or _PERFORMANCE.search(text):
        return None
    for name, pattern, _types in _KINDS:
        if pattern.search(text):
            return name
    return "week" if _WEEK.search(text) or "calendar" in text or "schedule" in text else None


def _counted(texts: List[str]) -> List[str]:
    """Identical entries once, with a count ("Homework due: Science (2)"), keeping first-seen order."""
    counts: Dict[str, int] = {}
    for text in texts:
        counts[text] = counts.get(text, 0) + 1
    return [text if n == 1 else f"{text} ({n})" for text, n in counts.items()]


def _when(value: str) -> str:
    def one(iso: str) -> str:
        d = parse_day(iso)
        return d.strftime("%a, %d %b %Y").replace(" 0", " ") if d else iso
    if " to " in value:
        start, end = value.split(" to ", 1)
        return f"{one(start)} to {one(end)}"
    return one(value)


def calendar_answer(intent: str, items: List[Dict[str, Any]], today: date, role: Optional[str] = None) -> str:
    """A plain answer for a calendar question from role-scoped items (each {date, type, title, detail})."""
    shown = [i for i in items if i["type"] not in ("lost", "session")]
    # A parent asks about their child's calendar.
    whose, lead = ("your child's", "Your child's next") if role == "parent" else ("your", "Your next")
    if intent == "week":
        week_end = (today + timedelta(days=7)).isoformat()
        soon = [i for i in shown if i["date"][:10] <= week_end]
        if not soon:
            return f"Nothing is on {whose} calendar for the next 7 days."
        rows = _counted([f"{_when(i['date'])}: {i['title']}" for i in soon])
        lines = [f"- {row}" for row in rows[:8]]
        more = f"\n…and {len(rows) - 8} more on the Calendar page." if len(rows) > 8 else ""
        return "Coming up in the next 7 days:\n" + "\n".join(lines) + more
    types = next(t for name, _p, t in _KINDS if name == intent)
    label = {"holiday": "holiday or vacation", "deadline": "homework or deadline", "exam": "exam or test",
             "event": "school event", "task": "task of your own"}[intent]
    matching = [i for i in shown if i["type"] in types]
    if not matching:
        return f"There is no {label} on {whose} calendar in the next {CALENDAR_LOOKAHEAD_DAYS // 30} months."
    first = matching[0]["date"]
    same_day = _counted([i["title"] for i in matching if i["date"] == first])
    names = same_day[0] if len(same_day) == 1 else ", ".join(same_day[:-1]) + f" and {same_day[-1]}"
    answer = f"{lead} {label}: {names}, on {_when(first)}."
    later = [i for i in matching if i["date"] != first][:2]
    if later:
        answer += " After that: " + "; ".join(f"{i['title']} ({_when(i['date'])})" for i in later) + "."
    return answer
