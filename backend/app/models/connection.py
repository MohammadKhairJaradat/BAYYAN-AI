from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from collections.abc import AsyncGenerator

from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.SQL_ECHO,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


async def init_db() -> None:
    from app.models.database import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
