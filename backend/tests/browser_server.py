"""Test-only server. Refuses to seed anything outside a fresh browser-test temp directory."""
import asyncio
import os
from pathlib import Path
import tempfile


def isolated_paths():
    root=Path(os.environ['LUMENEIOS_E2E_DIR']).resolve()
    if root.parent!=Path(tempfile.gettempdir()).resolve() or not root.name.startswith('lumen-browser-'):
        raise RuntimeError('Browser fixtures require an isolated system-temp directory.')
    url=os.environ.get('DATABASE_URL','')
    prefix='sqlite+aiosqlite:///'
    if not url.startswith(prefix):raise RuntimeError('Browser fixtures require isolated SQLite.')
    database=Path(url[len(prefix):]).resolve()
    storage=Path(os.environ['STORAGE_LOCAL_DIR']).resolve()
    if not database.is_relative_to(root) or not storage.is_relative_to(root):
        raise RuntimeError('Browser fixture database/storage paths escaped the test directory.')
    if database.exists() or storage.exists():
        raise RuntimeError("Browser fixtures must never overwrite an existing database or upload directory.")
    return root


def main():
    isolated_paths()  # before app/settings/storage imports or database access
    os.environ['DEMO_MODE']='false'
    from backend.app.main import app
    from backend.app.db.session import AsyncSessionLocal,init_db,engine
    from backend.app.seed.seed_data import seed_database_if_empty
    from backend.app.core.security import get_password_hash
    from backend.app.models.entities import User
    from sqlalchemy import select
    async def fixtures():
        await init_db()
        async with AsyncSessionLocal() as session:
            await seed_database_if_empty(session)
            # Same full syllabus and default topic requirements a real installation initialises at startup
            # (skipped by the app because this server runs with DEMO_MODE off).
            from backend.app.services.syllabus_seed import initialise_curriculum
            await initialise_curriculum(session)
            hashed=get_password_hash('browser-test-password')
            for user in (await session.execute(select(User))).scalars():user.hashed_password=hashed
            await session.commit()
        await engine.dispose()
    asyncio.run(fixtures())
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=18080)


if __name__=='__main__':main()
