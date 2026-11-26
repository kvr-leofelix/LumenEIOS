import os
from typing import List, Optional
from pydantic import AnyHttpUrl, SecretStr, field_validator, model_validator, Field
from pathlib import Path
from urllib.parse import urlsplit
from pydantic_settings import BaseSettings, SettingsConfigDict

# Prefer apps/lumeneios/.env (stable across uvicorn cwd), then a cwd-relative .env.
# Process environment variables still override both files.
_APP_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILES = (str(_APP_ROOT / ".env"), ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True
    )

    APP_NAME: str = "LumenEIOS"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, v):
        if isinstance(v, str):
            if v.lower() in ("1", "true", "yes", "on", "dev", "development"):
                return True
            if v.lower() in ("0", "false", "no", "off", "release", "prod", "production"):
                return False
        return bool(v)
    SECRET_KEY: str = "lumeneios-super-secure-production-ready-secret-key-32charsmin!"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALGORITHM: str = "HS256"

    # Database configuration: defaults to SQLite+aiosqlite for zero-dependency local runs,
    # or PostgreSQL (postgresql+asyncpg://...) in Docker/Production
    DATABASE_URL: str = "sqlite+aiosqlite:///./lumeneios.db"

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173"
    ]

    ALLOWED_HOSTS: List[str] = ["localhost", "127.0.0.1", "testserver"]

    # Object storage / MinIO
    S3_ENDPOINT_URL: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET_NAME: str = "lumeneios-documents"
    STORAGE_LOCAL_DIR: str = "./storage_uploads"

    # OCR & ML Configuration
    ACTIVE_OCR_PROVIDER: str = "simulated"  # "simulated", "huggingface", "trocr", "paddleocr"
    OCR_CONFIDENCE_THRESHOLD: float = 0.85
    HF_TOKEN: str = ""
    DEFAULT_VISION_MODEL: str = "microsoft/trocr-base-handwritten"

    # LLM Provider
    LLM_PROVIDER: str = "deterministic"  # "deterministic", "huggingface", "hosted"
    LEARNSPHERE_MIN_OBSERVATIONS: int = Field(default=3, ge=1, le=1000)
    LEARNSPHERE_MIN_ACTIVITIES: int = Field(default=2, ge=1, le=1000)
    LEARNSPHERE_RECENT_OBSERVATIONS: int = Field(default=20, ge=1, le=1000)
    LEARNSPHERE_SUPPORT_THRESHOLD: float = Field(default=65, ge=0, le=100)
    LLM_API_KEY: str = ""

    # Gemini (AI question generation preview). Read from the environment only; the key is a
    # SecretStr so it never appears in settings reprs, logs or errors. Empty = AI disabled.
    GEMINI_API_KEY: SecretStr = SecretStr("")
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    # Text-only LearnSphere / Question Studio steps (Teach-Back feedback, written marking, Panchapadi, competency
    # analysis, guidance): "qwen" (local GPU, default) or "gemini" (cloud, faster). Images always use Qwen.
    LEARNSPHERE_TEXT_PROVIDER: str = "qwen"
    AI_REQUEST_TIMEOUT_SECONDS: float = 60.0

    # Local Qwen model for Question Studio Beta and the assistant.
    QWEN_VL_MODEL_ID: str = "Qwen/Qwen2.5-VL-3B-Instruct-AWQ"

    # Optional Neo4j Knowledge Graph
    NEO4J_ENABLED: bool = False
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Demo mode: seeds sample accounts (password demo123) and enables demo shortcuts.
    DEMO_MODE: bool = True
    # Fill any missing syllabus topics / default teacher plans at startup (additive, idempotent). Tests that exercise the small
    # research crosswalk switch it off; the explicit command backend.scripts.init_curriculum works either way.
    AUTO_SEED_CURRICULUM: bool = True
    # Fixed planning date (YYYY-MM-DD) for tests/demos; unset = the server's current date. Remaining-syllabus recalculation counts only
    # instructional days after this date.
    PLANNING_TODAY: Optional[str] = None
    # Development root login: LEOFELIX or leofelix@lumeneios.demo.
    # Defaults to the password shown on the sign-in page. Blank or production disables it.
    DEMO_ROOT_PASSWORD: SecretStr | None = SecretStr("KVR")
    # Developer bypass on the sign-in page (pick any account, no password). Only honoured when APP_ENV=development.
    DEV_LOGIN_BYPASS: bool = True

    @property
    def demo_root_password(self) -> str | None:
        if self.APP_ENV.lower() != "development":
            return None
        if self.DEMO_ROOT_PASSWORD is None:
            return None
        configured = self.DEMO_ROOT_PASSWORD.get_secret_value().strip()
        return configured or None

    @property
    def demo_root_enabled(self) -> bool:
        return self.demo_root_password is not None

    @model_validator(mode="after")
    def production_configuration(self):
        if self.APP_ENV.lower() not in {"production", "prod"}:
            return self
        problems = []
        if self.DEMO_MODE: problems.append("DEMO_MODE must be false")
        if self.DEBUG: problems.append("DEBUG must be false")
        if self.SECRET_KEY == type(self).model_fields["SECRET_KEY"].default or len(self.SECRET_KEY) < 32 or "<" in self.SECRET_KEY:
            problems.append("SECRET_KEY must be explicitly provisioned with at least 32 characters")
        if not self.DATABASE_URL.startswith("postgresql+asyncpg://"):
            problems.append("DATABASE_URL must target a PostgreSQL staging-verified database")
        if "BACKEND_CORS_ORIGINS" not in self.model_fields_set or not self.BACKEND_CORS_ORIGINS or any(
            urlsplit(origin).scheme != "https" or urlsplit(origin).path not in {"", "/"} or not urlsplit(origin).hostname
            or urlsplit(origin).username is not None or urlsplit(origin).query or urlsplit(origin).fragment or "*" in origin for origin in self.BACKEND_CORS_ORIGINS):
            problems.append("BACKEND_CORS_ORIGINS must be explicit exact HTTPS origins")
        if "ALLOWED_HOSTS" not in self.model_fields_set or not self.ALLOWED_HOSTS or any(
            not host.strip() or "*" in host or "/" in host or ":" in host for host in self.ALLOWED_HOSTS):
            problems.append("ALLOWED_HOSTS must be explicit host names")
        if "STORAGE_LOCAL_DIR" not in self.model_fields_set or not Path(self.STORAGE_LOCAL_DIR).is_absolute():
            problems.append("STORAGE_LOCAL_DIR must be an explicit absolute private directory")
        if problems:
            raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        return self


settings = Settings()
