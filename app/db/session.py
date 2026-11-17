from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def make_session_pool(database_url: str) -> async_sessionmaker[AsyncSession]:
    """Фабрика пула сессий: движок создаётся на процесс (бот или celery-воркер)."""
    engine = create_async_engine(database_url, pool_pre_ping=True)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
