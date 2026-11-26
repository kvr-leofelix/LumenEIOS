"""Databases created before Qwen marking existed reject source='qwen'. init_db widens the CHECK constraint once,
keeping every stored suggestion (SQLite rebuilds the leaf table)."""
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.db.session import _allow_all_suggestion_sources
from backend.app.modules.differentiated_homework.models import HomeworkEvaluationSuggestionRecord

TABLE = HomeworkEvaluationSuggestionRecord.__table__.name
COLUMNS = ("id, evaluation_id, draft_item_id, position, suggested_marks, max_marks, correctness, explanation, feedback, "
           "confidence, needs_teacher_attention, source, created_by, created_at, updated_at")


def row(i, source):
    return (f"('s{i}', 'e1', 'd{i}', {i}, 1, 2, 'correct', 'why', 'fb', 'high', 0, '{source}', 'u1', "
            "'2026-11-18 10:00:00', '2026-11-18 10:00:00')")


@pytest.mark.asyncio
async def test_old_sqlite_constraint_is_widened_and_rows_are_kept(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'old.db'}")
    async with engine.begin() as conn:
        # The table as databases created before this change have it (no 'qwen').
        await conn.execute(text(f"""CREATE TABLE {TABLE} (
            id VARCHAR(64) NOT NULL PRIMARY KEY, evaluation_id VARCHAR(64) NOT NULL, draft_item_id VARCHAR(64) NOT NULL,
            position INTEGER NOT NULL, suggested_marks INTEGER NOT NULL, max_marks INTEGER NOT NULL,
            correctness VARCHAR(32) NOT NULL, explanation TEXT NOT NULL, feedback TEXT NOT NULL, rubric_criteria_json JSON,
            confidence VARCHAR(16) NOT NULL, needs_teacher_attention BOOLEAN NOT NULL, source VARCHAR(32) NOT NULL,
            model VARCHAR(128), created_by VARCHAR(64) NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL,
            CONSTRAINT ck_homework_eval_ai_suggestions_source CHECK (source IN ('deterministic_mcq', 'gemini', 'teacher_required')))"""))
        await conn.execute(text(f"CREATE INDEX ix_{TABLE}_evaluation_id ON {TABLE} (evaluation_id)"))
        await conn.execute(text(f"INSERT INTO {TABLE} ({COLUMNS}) VALUES {row(1, 'gemini')}"))
        with pytest.raises(Exception):
            async with conn.begin_nested():
                await conn.execute(text(f"INSERT INTO {TABLE} ({COLUMNS}) VALUES {row(2, 'qwen')}"))

    for _ in range(2):  # the second run must be a no-op
        async with engine.begin() as conn:
            await _allow_all_suggestion_sources(conn)

    async with engine.begin() as conn:
        await conn.execute(text(f"INSERT INTO {TABLE} ({COLUMNS}) VALUES {row(2, 'qwen')}"))
        rows = (await conn.execute(text(f"SELECT id, source FROM {TABLE} ORDER BY id"))).all()
        assert [tuple(r) for r in rows] == [("s1", "gemini"), ("s2", "qwen")]
        with pytest.raises(Exception):  # unknown sources are still refused
            async with conn.begin_nested():
                await conn.execute(text(f"INSERT INTO {TABLE} ({COLUMNS}) VALUES {row(3, 'gpt')}"))
        leftovers = (await conn.execute(text("SELECT name FROM sqlite_master WHERE name LIKE '%before_qwen%'"))).all()
        assert leftovers == []
    await engine.dispose()
