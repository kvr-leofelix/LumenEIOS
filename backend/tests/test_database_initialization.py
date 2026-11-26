"""The inherited optional-column upgrade is repeatable and does not discard records."""
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine
import backend.app.db.session as session_module


@pytest.mark.asyncio
async def test_existing_document_upgrade_is_repeatable_and_preserves_rows(monkeypatch):
    engine=create_async_engine('sqlite+aiosqlite:///:memory:')
    try:
        async with engine.begin() as connection:
            await connection.execute(text('CREATE TABLE documents (id VARCHAR(64) PRIMARY KEY)'))
            await connection.execute(text("INSERT INTO documents (id) VALUES ('preserved')"))
        monkeypatch.setattr(session_module,'engine',engine)
        await session_module.init_db()
        await session_module.init_db()
        async with engine.begin() as connection:
            columns=await connection.run_sync(lambda sync:{c['name'] for c in inspect(sync).get_columns('documents')})
            assert {'subject_id','doc_type','content_hash','extracted_text'} <= columns
            assert (await connection.execute(text('SELECT id FROM documents'))).scalars().all() == ['preserved']
    finally:
        await engine.dispose()
