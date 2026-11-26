"""Developer portal: platform health, sample roster, flags, and the model workshop.

These routes require a development root session that is currently presenting the
developer role. School staff cannot open them. Feature-flag reads are the exception:
every signed-in role needs them so a disabled beta stays hidden.
"""
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import get_current_user, oauth2_scheme
from backend.app.core.config import settings
from backend.app.services.ai_gateway import (
    AIGatewayError,
    AINotConfigured,
    active_gemini_model,
    list_gemini_models,
    select_gemini_model,
)
from backend.app.core.security import decode_token
from backend.app.db.session import AsyncSessionLocal, Base, engine, get_db
from backend.app.models.entities import (
    ClassSection,
    CompetencyOutcome,
    ImpersonationEvent,
    School,
    SchoolFeatureFlag,
    Student,
    StudentOcrHistory,
    Subject,
    User,
    WorkshopRun,
    utc_now,
)
from backend.app.modules.differentiated_homework import models as _homework_models  # noqa: F401
from backend.app.seed.seed_data import DEFAULT_PASSWORD, seed_database_if_empty

router = APIRouter(prefix="/developer", tags=["Developer"])

FLAG_KEYS = ("question_studio", "upload_beta", "answer_sheet_ocr", "presentation_ui")
FlagKey = Literal["question_studio", "upload_beta", "answer_sheet_ocr", "presentation_ui"]

OUTCOME_SEEDS = [
    ("LU", "Recall the idea and explain it in their own words."),
    ("CU", "Use the idea on a familiar classroom problem."),
    ("AU", "Carry the idea into a situation they have not practised."),
    ("CT", "Judge a solution and say why it holds or fails."),
]


def require_developer(
    current_user: User = Depends(get_current_user),
    token: str | None = Depends(oauth2_scheme),
) -> User:
    payload = decode_token(token) if token else {}
    if not (settings.demo_root_enabled and payload.get("demo_root") and payload.get("role") == "developer"):
        raise HTTPException(status_code=403, detail="A developer session is required.")
    return current_user


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


async def ensure_outcomes(db: AsyncSession) -> None:
    existing = await db.scalar(select(func.count()).select_from(CompetencyOutcome))
    if existing:
        return
    for grade in (6, 8, 10):
        for domain, statement in OUTCOME_SEEDS:
            db.add(CompetencyOutcome(
                code=f"{domain}-{grade}",
                domain=domain,
                grade=grade,
                statement=statement,
            ))
    await db.commit()


def _flags_for(rows: list[SchoolFeatureFlag], school_id: str) -> dict[str, bool]:
    saved = {row.flag_key: row.enabled for row in rows if row.school_id == school_id}
    return {key: bool(saved.get(key, True)) for key in FLAG_KEYS}


class FlagUpdate(BaseModel):
    school_id: str
    flag_key: FlagKey
    enabled: bool


class OutcomeWrite(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    domain: Literal["LU", "CU", "AU", "CT"]
    grade: int = Field(ge=1, le=12)
    statement: str = Field(min_length=8, max_length=500)


class WorkshopRequest(BaseModel):
    kind: Literal["ocr", "question"]
    text: str = Field(min_length=1, max_length=4000)
    competency_code: str | None = Field(default=None, max_length=32)


class ReseedRequest(BaseModel):
    confirm: str


def preview_workshop(body: WorkshopRequest) -> dict:
    """A local preview. It does not call the vision model or a hosted LLM."""
    lines = [line.strip() for line in body.text.splitlines() if line.strip()]
    if body.kind == "ocr":
        return {
            "blocks": [{"text": line, "confidence": 0.92} for line in lines] or [{"text": body.text.strip(), "confidence": 0.92}],
            "note": "Deterministic preview. The configured vision model was not called.",
        }
    code = (body.competency_code or "CU").strip() or "CU"
    source = lines[0] if lines else body.text.strip()
    return {
        "competency": code,
        "question": f"[{code}] {source}",
        "note": "Deterministic preview. The question model was not called.",
    }


def backup_sqlite() -> str | None:
    parsed = make_url(settings.DATABASE_URL)
    if not parsed.drivername.startswith("sqlite") or not parsed.database or parsed.database == ":memory:":
        return None
    source = Path(parsed.database).resolve()
    if not source.exists():
        return None
    target = source.with_name(f"{source.name}.backup-{datetime.now():%Y%m%d-%H%M%S}")
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    return str(target)


@router.get("/health")
async def platform_health(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_developer),
):
    await db.execute(text("SELECT 1"))
    scans = await db.scalar(select(func.count()).select_from(StudentOcrHistory)) or 0
    last_scan = await db.scalar(
        select(StudentOcrHistory.created_at).order_by(StudentOcrHistory.created_at.desc()).limit(1)
    )
    runs = await db.scalar(select(func.count()).select_from(WorkshopRun)) or 0
    return {
        "api": "up",
        "database": "up",
        "environment": settings.APP_ENV,
        "ocr": {
            "model": settings.DEFAULT_VISION_MODEL,
            "stored_scans": scans,
            "last_scan": _iso(last_scan),
        },
        "question_model": {
            "provider": settings.LLM_PROVIDER,
            "model": settings.QWEN_VL_MODEL_ID,
            "workshop_runs": runs,
        },
    }


@router.get("/roster")
async def roster(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_developer),
):
    schools = {school.id: school.name for school in (await db.scalars(select(School))).all()}
    users = (await db.scalars(select(User).order_by(User.role, User.name))).all()
    return {
        "sample_password": DEFAULT_PASSWORD,
        "root_login": "LEOFELIX",
        "accounts": [
            {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "role": user.role,
                "school": schools.get(user.school_id or "", ""),
            }
            for user in users
        ],
    }


@router.post("/roster/reseed")
async def reseed_roster(
    body: ReseedRequest,
    _: User = Depends(require_developer),
):
    if settings.APP_ENV != "development":
        raise HTTPException(status_code=403, detail="Reseed is available only in development.")
    if body.confirm != "reset":
        raise HTTPException(status_code=400, detail="Type reset to replace the sample roster.")
    backup = backup_sqlite()
    async with engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            await conn.execute(text("PRAGMA foreign_keys=OFF"))
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
    async with AsyncSessionLocal() as session:
        await seed_database_if_empty(session)
    return {
        "reseeded": True,
        "backup": backup,
        "sample_password": DEFAULT_PASSWORD,
        "message": "Sample roster restored. Sign in again. The previous developer session no longer exists.",
    }


@router.get("/flags")
async def list_flags(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_developer),
):
    schools = (await db.scalars(select(School).where(School.is_archived == False).order_by(School.name))).all()  # noqa: E712
    rows = (await db.scalars(select(SchoolFeatureFlag))).all()
    return {
        "keys": [
            {"key": "question_studio", "label": "AI Question Studio"},
            {"key": "upload_beta", "label": "Upload"},
            {"key": "answer_sheet_ocr", "label": "Answer Sheet OCR"},
            {"key": "presentation_ui", "label": "Presentation interface"},
        ],
        "schools": [
            {"id": school.id, "name": school.name, "flags": _flags_for(list(rows), school.id)}
            for school in schools
        ],
    }


@router.put("/flags")
async def update_flag(
    body: FlagUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_developer),
):
    school = await db.get(School, body.school_id)
    if not school:
        raise HTTPException(status_code=404, detail="School not found.")
    row = await db.scalar(
        select(SchoolFeatureFlag).where(
            SchoolFeatureFlag.school_id == body.school_id,
            SchoolFeatureFlag.flag_key == body.flag_key,
        )
    )
    if row is None:
        row = SchoolFeatureFlag(school_id=body.school_id, flag_key=body.flag_key, enabled=body.enabled)
        db.add(row)
    else:
        row.enabled = body.enabled
    await db.commit()
    return {"school_id": body.school_id, "flag_key": body.flag_key, "enabled": body.enabled}


@router.get("/flags/active")
async def active_flags(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    token: str | None = Depends(oauth2_scheme),
):
    payload = decode_token(token) if token else {}
    if payload.get("demo_root") and payload.get("role") == "developer":
        return {key: True for key in FLAG_KEYS}
    school_id = payload.get("school_id") or current_user.school_id
    if not school_id:
        return {key: True for key in FLAG_KEYS}
    rows = (await db.scalars(select(SchoolFeatureFlag).where(SchoolFeatureFlag.school_id == school_id))).all()
    return _flags_for(list(rows), school_id)


@router.get("/access")
async def access_log(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_developer),
):
    events = (
        await db.scalars(select(ImpersonationEvent).order_by(ImpersonationEvent.created_at.desc()).limit(50))
    ).all()
    schools = {school.id: school.name for school in (await db.scalars(select(School))).all()}
    return [
        {
            "id": event.id,
            "actor_name": event.actor_name,
            "from_role": event.from_role,
            "to_role": event.to_role,
            "school": schools.get(event.school_id or "", ""),
            "created_at": _iso(event.created_at),
        }
        for event in events
        if event.from_role != event.to_role
    ]


@router.get("/framework")
async def list_outcomes(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_developer),
):
    await ensure_outcomes(db)
    rows = (await db.scalars(select(CompetencyOutcome).order_by(CompetencyOutcome.grade, CompetencyOutcome.domain))).all()
    return [
        {
            "id": row.id,
            "code": row.code,
            "domain": row.domain,
            "grade": row.grade,
            "statement": row.statement,
            "version": row.version,
        }
        for row in rows
    ]


@router.post("/framework", status_code=201)
async def create_outcome(
    body: OutcomeWrite,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_developer),
):
    code = body.code.strip().upper()
    if await db.scalar(select(CompetencyOutcome).where(CompetencyOutcome.code == code)):
        raise HTTPException(status_code=409, detail="That outcome code already exists.")
    row = CompetencyOutcome(code=code, domain=body.domain, grade=body.grade, statement=body.statement.strip())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"id": row.id, "code": row.code, "domain": row.domain, "grade": row.grade, "statement": row.statement, "version": row.version}


@router.put("/framework/{outcome_id}")
async def update_outcome(
    outcome_id: str,
    body: OutcomeWrite,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_developer),
):
    row = await db.get(CompetencyOutcome, outcome_id)
    if not row:
        raise HTTPException(status_code=404, detail="Outcome not found.")
    row.domain = body.domain
    row.grade = body.grade
    row.statement = body.statement.strip()
    row.version = (row.version or 1) + 1
    row.updated_at = utc_now()
    await db.commit()
    return {"id": row.id, "code": row.code, "domain": row.domain, "grade": row.grade, "statement": row.statement, "version": row.version}


@router.get("/quality")
async def data_quality(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_developer),
):
    await ensure_outcomes(db)
    schools = (await db.scalars(select(School).where(School.is_archived == False))).all()  # noqa: E712
    users = {user.id: user for user in (await db.scalars(select(User))).all()}
    classes = (await db.scalars(select(ClassSection))).all()
    students = (await db.scalars(select(Student))).all()
    subjects = (await db.scalars(select(Subject))).all()
    grades = set((await db.scalars(select(CompetencyOutcome.grade))).all())
    names = {school.id: school.name for school in schools}
    return {
        "schools_missing_principal": [
            {"id": school.id, "name": school.name}
            for school in schools
            if not school.principal_id or school.principal_id not in users
        ],
        "classes_missing_teacher": [
            {"id": section.id, "name": section.name, "school": names.get(section.school_id, "")}
            for section in classes
            if not section.class_teacher_id or section.class_teacher_id not in users
        ],
        "students_missing_parent": [
            {"id": student.id, "name": student.name, "school": names.get(student.school_id, "")}
            for student in students
            if not student.parent_id or student.parent_id not in users
        ],
        "subjects_without_outcome": [
            {"id": subject.id, "name": subject.name, "grade": subject.grade}
            for subject in subjects
            if subject.grade not in grades
        ],
    }


@router.post("/workshop")
async def run_workshop(
    body: WorkshopRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_developer),
):
    result = preview_workshop(body)
    row = WorkshopRun(kind=body.kind, prompt=body.text.strip(), result_json=result, status="completed")
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"id": row.id, "kind": row.kind, "status": row.status, "result": result, "created_at": _iso(row.created_at)}


class GeminiModelRequest(BaseModel):
    model: str = Field(min_length=1, max_length=120)


@router.get("/gemini/models")
async def gemini_models(_: User = Depends(require_developer)):
    try:
        models = await list_gemini_models()
    except AINotConfigured as exc:
        raise HTTPException(status_code=503, detail=exc.public_message) from exc
    except AIGatewayError as exc:
        raise HTTPException(status_code=502, detail=exc.public_message) from exc
    current = active_gemini_model()
    if current not in {item["id"] for item in models}:
        models.insert(0, {"id": current, "label": current})
    return {"current": current, "models": models}


@router.put("/gemini/model")
async def choose_gemini_model(body: GeminiModelRequest, _: User = Depends(require_developer)):
    try:
        models = await list_gemini_models()
    except AINotConfigured as exc:
        raise HTTPException(status_code=503, detail=exc.public_message) from exc
    except AIGatewayError as exc:
        raise HTTPException(status_code=502, detail=exc.public_message) from exc
    allowed = {item["id"] for item in models}
    allowed.add(settings.GEMINI_MODEL)
    chosen = body.model.strip()
    if chosen not in allowed:
        raise HTTPException(status_code=422, detail="Choose a Gemini model from the list.")
    return {"current": select_gemini_model(chosen)}


@router.get("/releases")
async def release_notes(_: User = Depends(require_developer)):
    return [
        {
            "version": "2026.11",
            "title": "Developer portal",
            "points": [
                "Platform health shows the API, database, OCR model, and question model without calling them.",
                "Sample accounts and a confirmed roster reseed keep the sign-in page and the database aligned.",
                "Question Studio, Upload, answer-sheet OCR, and the Presentation interface can be turned off per school.",
                "Role switches are recorded, and a developer session is labelled while it is viewing another role.",
            ],
        },
        {
            "version": "2026.10",
            "title": "School walkthrough",
            "points": [
                "Management can open a school and see its teachers, students, and monthly performance.",
                "Principals add classes, teachers, and students. Teachers review homework. Students try answer-sheet OCR.",
                "Presentation theme and presentation interface sit in the theme menu for a live demo.",
            ],
        },
    ]
