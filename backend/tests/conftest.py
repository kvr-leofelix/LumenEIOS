import hashlib
import os
import shutil
import tempfile
import warnings
from pathlib import Path
from typing import Dict

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import AsyncSession

# ------------------------------------------------------------------------------
# TEST ISOLATION: this block must stay above every backend.app import.
#
# Settings and the database engine are built when their modules are imported, and
# importing storage_service creates the upload directory. Redirecting them later
# would be too late, so each run gets a throwaway folder first, and the paths are
# checked before the application is imported.
# ------------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
ORIGINAL_DB = REPO_ROOT / "lumeneios.db"
ORIGINAL_UPLOADS = REPO_ROOT / "storage_uploads"


class IsolationError(RuntimeError):
    """Raised when tests could touch real project data. Aborts the run."""


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_originals() -> Dict[str, str]:
    """Map each original path, relative to the repo, to its SHA-256 ("<dir>" for folders)."""
    snapshot = {
        path.relative_to(REPO_ROOT).as_posix(): _file_sha256(path)
        for path in REPO_ROOT.glob("lumeneios.db*")
        if path.is_file()
    }
    if ORIGINAL_UPLOADS.is_dir():
        snapshot[ORIGINAL_UPLOADS.relative_to(REPO_ROOT).as_posix()] = "<dir>"
        for path in ORIGINAL_UPLOADS.rglob("*"):
            relative = path.relative_to(REPO_ROOT).as_posix()
            snapshot[relative] = "<dir>" if path.is_dir() else _file_sha256(path)
    return snapshot


def _assert_strictly_inside(path, root: Path, label: str) -> Path:
    resolved = Path(path).resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise IsolationError(f"{label} is not inside the test directory {root}: {resolved}")
    return resolved


def _assert_isolated(db_url, upload_dir) -> None:
    """Fail closed unless the database file and upload folder are inside TEST_DIR."""
    try:
        url = make_url(db_url)
    except ArgumentError as exc:
        raise IsolationError("Test database URL could not be parsed.") from exc

    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise IsolationError(
            f"Tests require a SQLite database file, got backend '{url.get_backend_name()}'."
        )

    db_path = _assert_strictly_inside(url.database, TEST_DIR, "Test database")
    uploads = _assert_strictly_inside(upload_dir, TEST_DIR, "Test upload directory")
    if db_path == ORIGINAL_DB or uploads.is_relative_to(ORIGINAL_UPLOADS):
        raise IsolationError("Test paths point at original project data.")


def _assert_originals_unchanged() -> None:
    current = _snapshot_originals()
    added = sorted(set(current) - set(ORIGINAL_SNAPSHOT))
    removed = sorted(set(ORIGINAL_SNAPSHOT) - set(current))
    changed = sorted(
        path for path in set(current) & set(ORIGINAL_SNAPSHOT)
        if current[path] != ORIGINAL_SNAPSHOT[path]
    )
    if added or removed or changed:
        raise IsolationError(
            f"Original project data changed. Added: {added}; removed: {removed}; changed: {changed}."
        )


ORIGINAL_SNAPSHOT = _snapshot_originals()

# Checked before mkdtemp so a temp location inside the repo never gets written to.
if Path(tempfile.gettempdir()).resolve().is_relative_to(REPO_ROOT):
    raise IsolationError("The system temp directory is inside the repository.")

TEST_DIR = Path(tempfile.mkdtemp(prefix="lumeneios-tests-")).resolve()

# Assigned rather than defaulted, so these also override any exported value or .env file.
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(TEST_DIR / 'test.db').as_posix()}"
os.environ["STORAGE_LOCAL_DIR"] = str(TEST_DIR / "uploads")
os.environ["DEMO_MODE"] = "true"  # Exercise the legacy demo paths in the isolated test app.
os.environ["AUTO_SEED_CURRICULUM"] = "false"  # tests build their own topic sets; the seed has its own tests (test_syllabus_seed.py).
os.environ["PLANNING_TODAY"] = "2026-03-31"  # fixed planning date: fixtures use calendars that start on 1 April 2026

# Guard phase 1: config.py only reads settings, so nothing has been written or connected yet.
from backend.app.core.config import settings  # noqa: E402

_assert_isolated(settings.DATABASE_URL, settings.STORAGE_LOCAL_DIR)

from backend.app.main import app  # noqa: E402
from backend.app.core.security import create_access_token  # noqa: E402
from backend.app.db.session import engine, init_db, AsyncSessionLocal  # noqa: E402
from backend.tests.sample_seed import seed_database_if_empty  # noqa: E402
from backend.app.services.storage_service import storage_service  # noqa: E402

# Guard phase 2: check the live objects. The engine connects lazily, so it hasn't connected yet.
_assert_isolated(engine.url, storage_service.upload_dir)


def pytest_unconfigure(config):
    # Removes this run's temp folder only. A folder still held open is left in the system temp.
    shutil.rmtree(TEST_DIR, ignore_errors=True)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def prepare_database():
    _assert_isolated(engine.url, storage_service.upload_dir)
    await init_db()
    from backend.app.modules.learnsphere.models import LearningTopic
    from backend.app.db.session import Base
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=[
            t for t in Base.metadata.sorted_tables if t.name.startswith("learning_")]))
    async with AsyncSessionLocal() as session:
        await seed_database_if_empty(session)
    yield
    try:
        _assert_originals_unchanged()
    finally:
        try:
            await engine.dispose()
        except Exception as exc:
            # Must not hide a safety failure raised above.
            warnings.warn(f"Test engine disposal failed: {exc}")


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def isolate_automatic_stage_inference(monkeypatch):
    """New submission hooks must never send synthetic fixtures to a real model."""
    from backend.app.services.llm_service import qwen_question_studio
    import backend.app.services.panchapadi as stage_worker
    monkeypatch.setattr(stage_worker,"GUIDANCE_RETRY_DELAYS",(0,0))
    from backend.app.modules.learnsphere import automation
    async def isolated_competencies(questions, subject, topics):
        return [{"position":q["position"],"label":q.get("competency") if q.get("competency") in automation.CODES else None,
            "suggested_label":q.get("competency"),"confidence":0.95,"status":"provisional",
            "reason":"Synthetic test mapping for this question.","question_fingerprint":automation.question_fingerprint(q)}
            for q in questions]
    monkeypatch.setattr(automation,"classify_competencies",isolated_competencies)
    from backend.app.schemas.panchapadi import StageClassification
    async def no_unmeasured_stages(questions, answers, outcomes):
        return StageClassification(questions=[{"position": q["position"], "mappings": []} for q in questions])
    monkeypatch.setattr(qwen_question_studio, "classify_panchapadi", no_unmeasured_stages)
    from backend.app.schemas.assessment_learning import LearningDrafts
    from backend.app.services.llm_service import QwenQuestionStudioUnavailable
    async def no_live_written(question, response):
        raise QwenQuestionStudioUnavailable("Isolated test: no live model")
    async def isolated_drafts(evidence):
        position = (evidence.get("required_gap_positions") or [evidence["questions"][0]["position"]])[0]
        return LearningDrafts(drafts=[{"kind":kind,"positions":[position],"stage":"Bodh",
            "title":"Synthetic "+kind,"explanation":"Fixture evidence reference.","learning_tip":"Explain the method.",
            "scenario":"Safe classroom task.","instructions":"Explain the idea in your own words.",
            "expected_submission":"A written explanation.","objective":"Explain the concept.","rubric":"Check the reasoning."}
            for kind in ("support","teach_back","mission")])
    monkeypatch.setattr(qwen_question_studio, "mark_written_answer", no_live_written)
    monkeypatch.setattr(qwen_question_studio, "generate_assessment_learning", isolated_drafts)
    from backend.app.schemas.assessment_learning import QuestionGuidance
    async def isolated_question_guidance(question,response,outcome,stages):
        return QuestionGuidance(expected_concept="Explain the assessed concept." if question.get("correct_answer") else None,
            misunderstanding="A response-specific gap." if outcome.get("score") is not None and outcome["score"]<outcome["maximum"] else None,
            explanation="Explain the reasoning used for "+question["text"],activity="Try another example and explain each step.",practice_question="How would you justify your method?")
    monkeypatch.setattr(qwen_question_studio,"assessment_question_guidance",isolated_question_guidance)


@pytest.fixture
def admin_token() -> str:
    return create_access_token("user-admin", school_id="school-1", role="admin")


@pytest.fixture
def principal_token() -> str:
    return create_access_token("user-principal-1", school_id="school-1", role="principal")


@pytest.fixture
def teacher_token() -> str:
    return create_access_token("user-teacher-1", school_id="school-1", role="teacher")


@pytest.fixture
def student_token() -> str:
    return create_access_token("user-student-1", school_id="school-1", role="student")


@pytest.fixture
def parent_token() -> str:
    return create_access_token("user-parent-1", school_id="school-1", role="parent")


@pytest.fixture
def other_school_teacher_token() -> str:
    return create_access_token("user-teacher-3", school_id="school-3", role="teacher")

