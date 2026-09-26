import asyncio
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy import JSON, String

from app.models.database import Base
from app.models.connection import get_db
from app.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite://"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)

# Enable foreign key enforcement for SQLite
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# Map PostgreSQL-specific column types to SQLite-compatible equivalents
# so that Base.metadata.create_all works with SQLite.
from sqlalchemy.ext.compiler import compiles

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"

@compiles(UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "CHAR(32)"


TestSessionFactory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
async def setup_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionFactory() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Hand a test a direct DB session against the same in-memory engine the
    app uses. Lets tests mutate state (e.g. user.subscription_tier) without
    hitting an HTTP endpoint — useful since the self-serve tier-upgrade route
    is gone and tests still need to set up tier state for downstream checks.
    """
    async with TestSessionFactory() as session:
        yield session
