from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin,
    advisor,
    calendar,
    capabilities,
    chat_sessions,
    deductions,
    document_processing,
    documents,
    income_sources,
    notifications,
    rag,
    tax_calculations,
    tax_profiles,
    tax_workspace,
    users,
)
from app.auth.router import router as auth_router
from app.services.storage import get_storage
from app.voice.route_voice import router as voice_router
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage = get_storage()
    await storage.ensure_bucket()
    await storage.ensure_avatar_bucket()
    yield


app = FastAPI(
    title="BAYYAN | بيان",
    description="Tax preparation workspace for individual Jordanian taxpayers; not an official filing service",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN] + (["http://127.0.0.1:5173"] if settings.APP_ENV != "production" else []),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_v1 = "/api/v1"
app.include_router(auth_router, prefix=api_v1)
app.include_router(capabilities.router, prefix=api_v1)
app.include_router(users.router, prefix=api_v1)
app.include_router(tax_profiles.router, prefix=api_v1)
app.include_router(income_sources.router, prefix=api_v1)
app.include_router(deductions.router, prefix=api_v1)
app.include_router(documents.router, prefix=api_v1)
app.include_router(document_processing.router, prefix=api_v1)
app.include_router(tax_calculations.router, prefix=api_v1)
app.include_router(tax_workspace.router, prefix=api_v1)
app.include_router(rag.router, prefix=api_v1)
app.include_router(chat_sessions.router, prefix=api_v1)
app.include_router(advisor.router, prefix=api_v1)
app.include_router(calendar.router, prefix=api_v1)
app.include_router(notifications.router, prefix=api_v1)
app.include_router(admin.router, prefix=api_v1)
app.include_router(voice_router, prefix=api_v1)


@app.get("/health")
async def health():
    return {"status": "ok"}
