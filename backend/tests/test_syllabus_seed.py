"""Fresh-clone curriculum: full syllabus, persisted default Core/Non-Core for every eligible topic, idempotent, edit-safe."""
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.db.session import Base
from backend.app.models.entities import User
from backend.app.models.planning_workspace import PlanningWorkspaceRevision
from backend.app.models.teacher_planning import PlanTopic, TeacherTopicConfig, TeacherTopicCoverage
from backend.app.seed.seed_data import seed_database_if_empty
from backend.app.services import syllabus_seed as ss
from backend.app.services import teacher_plan_service as svc


@pytest_asyncio.fixture
async def db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'fresh.db').as_posix()}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        await seed_database_if_empty(s)
        yield s
    await engine.dispose()


async def count(db, model):
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


def test_source_file_has_the_full_structure():
    ds = ss.load_dataset()
    kinds = {}
    for n in ds["nodes"]:
        kinds[n["kind"]] = kinds.get(n["kind"], 0) + 1
    assert kinds == {"CHAPTER": 76, "TOPIC": 353, "SUBTOPIC": 102}
    assert len(ss.plan_topic_rows(ds)) == 415
    assert all(len(n["title"]) < 120 for n in ds["nodes"])  # headings only, never page text


@pytest.mark.asyncio
async def test_fresh_database_gets_whole_syllabus_and_every_topic_configured(db):
    out = await ss.initialise_curriculum(db)
    assert out["plan_topics_added"] == 415 and out["eligible_plans"] == 16 and out["plans_recalculated"] == 0  # defaults already match the 2+2 calendar
    assert out["calendars_aligned"] == 0  # the seed records each school's approved 2+2 calendar itself
    per = (await db.execute(select(PlanTopic.grade, PlanTopic.subject, func.count()).group_by(PlanTopic.grade, PlanTopic.subject))).all()
    assert sorted(per) == [(6, "Mathematics", 65), (6, "Science", 65), (7, "Mathematics", 65), (7, "Science", 78), (8, "Mathematics", 58), (8, "Science", 84)]
    # One configuration per topic for every (teacher, grade, subject) plan the roster defines.
    topics_per = {(g, sub): n for g, sub, n in per}
    expected = sum(topics_per[(g, sub)] for _s, _t, g, sub in await ss.teaching_assignments(db))
    assert await count(db, TeacherTopicConfig) == expected == await count(db, TeacherTopicCoverage)
    # every school's workspace carries the dataset the UI renders from
    assert await count(db, PlanningWorkspaceRevision) == 2
    # ineligible teachers (English, Chemistry) have no plan; each eligible teacher owns only their own subject
    owners = {(t, s) for t, s in (await db.execute(select(TeacherTopicConfig.teacher_id, TeacherTopicConfig.subject).distinct())).all()}
    from backend.app.seed.seed_data import SUBJECT_NAME, TEACHERS
    eligible = {(f"user-teacher-{t['key']}", SUBJECT_NAME[t["subject"]]) for t in TEACHERS
                if SUBJECT_NAME[t["subject"]] in ("Mathematics", "Science")}
    assert owners == eligible and ("user-teacher-priya", "English") not in owners


@pytest.mark.asyncio
async def test_defaults_follow_the_classification_rules(db):
    await ss.initialise_curriculum(db)
    for c in (await db.execute(select(TeacherTopicConfig))).scalars().all():
        total = c.core_periods + c.non_core_periods
        assert c.classification in ("core", "mixed", "non_core") and c.origin == "demo_default"
        if c.classification == "core":
            assert c.non_core_periods == 0
        elif c.classification == "non_core":
            assert c.core_periods == 0
        else:
            assert c.core_periods == -(-total * 2 // 3)


@pytest.mark.asyncio
async def test_rerun_creates_no_duplicates_and_keeps_teacher_edits(db):
    await ss.initialise_curriculum(db)
    configs_before = await count(db, TeacherTopicConfig)
    cfg = (await db.execute(select(TeacherTopicConfig).filter_by(teacher_id="user-teacher-garima", grade=6))).scalars().first()
    actor = (await db.execute(select(User).filter_by(id="user-teacher-garima"))).scalars().one()
    total = cfg.core_periods + cfg.non_core_periods
    target = "non_core" if cfg.classification != "non_core" else "core"
    items = [{"topic_key": cfg.topic_key, "classification": target, "core_periods": total if target == "core" else 0,
              "non_core_periods": 0 if target == "core" else total}]
    await svc.save_requirements(db, actor, cfg.school_id, cfg.teacher_id, cfg.academic_year, 6, "Science", items, "test")
    await svc.set_coverage(db, actor, cfg.school_id, cfg.teacher_id, cfg.academic_year, 6, "Science", cfg.topic_key, "done", None)
    await db.commit()
    again = await ss.initialise_curriculum(db)
    assert again == {"plan_topics_added": 0, "workspace_datasets_added": 0, "eligible_plans": 16, "plans_filled": 0, "calendars_aligned": 0, "plans_recalculated": 0}
    assert await count(db, TeacherTopicConfig) == configs_before and await count(db, PlanTopic) == 415
    kept = (await db.execute(select(TeacherTopicConfig).filter_by(id=cfg.id))).scalars().one()
    await db.refresh(kept)
    assert (kept.classification, kept.origin) == (target, "teacher")
    cov = (await db.execute(select(TeacherTopicCoverage).filter_by(teacher_id=cfg.teacher_id, topic_key=cfg.topic_key))).scalars().one()
    assert cov.status == "done"


@pytest.mark.asyncio
async def test_teacher_cannot_change_another_teachers_plan(db):
    await ss.initialise_curriculum(db)
    kam = (await db.execute(select(TeacherTopicConfig).filter_by(teacher_id="user-teacher-kamlesh", grade=6))).scalars().first()
    garima = (await db.execute(select(User).filter_by(id="user-teacher-garima"))).scalars().one()
    with pytest.raises(svc.PlanError):
        await svc.set_coverage(db, garima, kam.school_id, kam.teacher_id, kam.academic_year, 6, "Mathematics", kam.topic_key, "done", None)
