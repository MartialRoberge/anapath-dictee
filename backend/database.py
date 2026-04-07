"""Configuration de la connexion base de donnees PostgreSQL.

Fournit le moteur async SQLAlchemy et la session factory.
En mode developpement sans BDD, les operations sont silencieusement ignorees.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import get_settings


def _create_engine() -> AsyncEngine | None:
    """Cree le moteur async SQLAlchemy si DATABASE_URL est configure."""
    settings = get_settings()
    if not settings.database_url:
        return None

    is_sqlite: bool = settings.database_url.startswith("sqlite")
    kwargs: dict[str, object] = {"echo": False}

    if not is_sqlite:
        kwargs["pool_size"] = 5
        kwargs["max_overflow"] = 10

    return create_async_engine(settings.database_url, **kwargs)


_engine: AsyncEngine | None = _create_engine()

_session_factory: async_sessionmaker[AsyncSession] | None = (
    async_sessionmaker(_engine, expire_on_commit=False)
    if _engine is not None
    else None
)


async def get_db_session() -> AsyncGenerator[AsyncSession | None, None]:
    """Dependency FastAPI : fournit une session DB ou None si pas de BDD."""
    if _session_factory is None:
        yield None
        return
    async with _session_factory() as session:
        yield session


async def create_tables() -> None:
    """Cree les tables si elles n'existent pas (mode dev)."""
    if _engine is None:
        return
    from db_models import Base
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_engine() -> None:
    """Ferme le moteur async a l'arret de l'application."""
    if _engine is not None:
        await _engine.dispose()
