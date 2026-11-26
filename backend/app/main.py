from contextlib import asynccontextmanager, suppress
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
import asyncio
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.db.session import init_db, AsyncSessionLocal
from backend.app.api.v1.router import api_router
from backend.app.seed.seed_data import ensure_classic_demo_student_link, seed_database_if_empty


class _SkipSeed(Exception):
    pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    from pathlib import Path
    from backend.app.db.session import engine
    db_file = engine.url.database
    resolved = str(Path(db_file).resolve()) if db_file else ":memory:"
    app.state.database_path = resolved
    logger.info("LumenEIOS database file (resolved absolute path): %s", resolved)
    if Path(resolved).name in {"lumeneios.db", "lumeneios_acceptance.db", "lumeneios_planning_dev.db", "lumeneios_takeover_acceptance.db"}:
        logger.warning("This backend is bound to a PROTECTED database file (%s). Use an isolated working copy for development.", resolved)
    logger.info("Initializing LumenEIOS database tables...")
    await init_db()
    if settings.DEMO_MODE:
        async with AsyncSessionLocal() as session:
            await seed_database_if_empty(session)
            # Older classic demo DBs may lack StudentAccountLink; repair without reseeding.
            await ensure_classic_demo_student_link(session)
        # Full syllabus + default teacher plans: additive and idempotent (only fills what is missing), so every clone and every
        # upgraded database converges on the same curriculum without touching teacher edits or coverage.
        try:
            if not settings.AUTO_SEED_CURRICULUM:
                raise _SkipSeed
            from backend.app.services.syllabus_seed import initialise_curriculum
            async with AsyncSessionLocal() as session:
                logger.info("Curriculum initialisation: %s", await initialise_curriculum(session))
        except _SkipSeed:
            logger.info("Curriculum auto-initialisation disabled (AUTO_SEED_CURRICULUM=false).")
        except Exception:  # never block startup; the explicit command backend.scripts.init_curriculum reports the failure
            logger.exception("Curriculum initialisation failed; run `python -m backend.scripts.init_curriculum`.")
    logger.info("LumenEIOS Backend successfully started.")
    from backend.app.services.panchapadi import run_guidance_recovery
    recovery=asyncio.create_task(run_guidance_recovery(),name="assessment-guidance-recovery")
    try:
        yield
    finally:
        recovery.cancel()
        with suppress(asyncio.CancelledError):
            await recovery
        logger.info("LumenEIOS Backend shutting down.")


app = FastAPI(
    title=settings.APP_NAME,
    description="Adaptive EdTech Ecosystem Backend aligned with NEP 2020 Competency Standards",
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan
)

if settings.APP_ENV.lower() in {"production", "prod"}:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)


@app.exception_handler(SQLAlchemyError)
async def safe_database_error(request: Request, exc: SQLAlchemyError):
    # SQLAlchemy exception strings can include statement parameters (hashes, keys, answers).
    # Handle this known error class inside ExceptionMiddleware, without logging those values.
    logger.error("Database operation failed; request transaction was rolled back.")
    return JSONResponse(status_code=500, content={"detail": "Database operation failed."})


@app.exception_handler(RequestValidationError)
async def safe_validation_error(request: Request, exc: RequestValidationError):
    # Do not echo submitted passwords, keys, answers or non-finite numbers in validation errors.
    return JSONResponse(status_code=422, content={"detail": [
        {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]})


# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_origin_regex=(
        r"https?://(localhost|127\.0\.0\.1|\[::1\]|192\.168\.\d{1,3}\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3})(:\d+)?$"
        if settings.APP_ENV == "development"
        else None
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
async def health_check():
    if not await _database_available():
        return JSONResponse(status_code=503, content={"status": "unhealthy", "database": "unavailable"})
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "database": "connected"
    }


@app.get("/ready", tags=["Health"])
async def readiness_check():
    if not await _database_available():
        return JSONResponse(status_code=503, content={"ready": False})
    return {"ready": True}


async def _database_available():
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.warning("Database readiness check failed.")
        return False


# Mount API Router
app.include_router(api_router, prefix=settings.API_V1_STR)

