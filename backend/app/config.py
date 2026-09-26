from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator


BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    APP_ENV: Literal["development", "production"] = "development"
    FRONTEND_ORIGIN: str = "http://localhost:5173"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/taxai"
    SECRET_KEY: str = "change-me-to-a-random-secret"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = ""
    MINIO_SECRET_KEY: str = ""
    MINIO_BUCKET: str = "tax-documents"
    MINIO_AVATAR_BUCKET: str = "avatars"
    MINIO_PUBLIC_URL: str = "http://localhost:9000"
    MINIO_SECURE: bool = False
    SQL_ECHO: bool = False

    # Document extraction (Gemini primary, Claude vision fallback)
    EXTRACTION_GEMINI_MODEL: str = "gemini-2.5-flash"
    EXTRACTION_CLAUDE_MODEL: str = "claude-sonnet-4-20250514"
    EXTRACTION_CONFIDENCE_THRESHOLD: float = 0.65

    # RAG / vector store
    CHROMA_PERSIST_DIR: str = "./data/chromadb"
    KNOWLEDGE_BASE_DIR: str = "./backend/knowledge_base"
    EMBEDDING_MODEL: str = "intfloat/multilingual-e5-large"
    EMBEDDING_REVISION: str = ""
    RAG_COLLECTION_VERSION: int = 2

    # LLM API keys — all empty by default; populate in .env
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    GOOGLE_AI_API_KEY: str = ""

    # qa.py provider router
    LLM_PROVIDER: str = "groq"
    GEMINI_CHAT_MODEL: str = "gemini-2.5-flash"
    GEMINI_TITLE_MODEL: str = "gemini-2.5-flash"
    OPENAI_CHAT_MODEL: str = "gpt-5.4"
    OPENAI_TITLE_MODEL: str = "gpt-5.4"
    ANTHROPIC_CHAT_MODEL: str = "claude-opus-4-7"
    ANTHROPIC_TITLE_MODEL: str = "claude-opus-4-7"
    GROQ_CHAT_MODEL: str = "llama-3.1-8b-instant"
    GROQ_TITLE_MODEL: str = "llama-3.1-8b-instant"
    GEMINI_TRANSCRIBE_MODEL: str = "gemini-2.5-flash"

    # Advisor (LangGraph) — LLM provider/model for the three reasoning nodes
    ADVISOR_LLM_PROVIDER: str = "anthropic"
    ADVISOR_LLM_MODEL: str = "claude-opus-4-7"
    ADVISOR_LLM_MAX_TOKENS: int = 2048

    @model_validator(mode="after")
    def reject_insecure_production_secret(self):
        self.FRONTEND_ORIGIN = self.FRONTEND_ORIGIN.rstrip("/")
        if self.APP_ENV == "production" and (
            self.SECRET_KEY == "change-me-to-a-random-secret"
            or len(self.SECRET_KEY) < 32
        ):
            raise ValueError("Set a unique SECRET_KEY of at least 32 characters in production")
        if self.APP_ENV == "production" and not self.FRONTEND_ORIGIN.startswith("https://"):
            raise ValueError("FRONTEND_ORIGIN must use HTTPS in production")
        return self

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
