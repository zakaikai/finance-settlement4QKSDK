"""Test fixtures for async database tests."""
import os
import tempfile
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from backend.database import Base
from backend import auth, models  # ensure all models registered on Base.metadata


@pytest.fixture(autouse=True)
def _auth_disabled():
    """Point auth to an empty temp config so tests aren't blocked by middleware.

    Tests that exercise auth (test_auth.py, test_auth_api.py) override
    ``auth._CONFIG_PATH`` in their own setup — this autouse fixture
    simply ensures a clean baseline for everything else.
    """
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".env", mode="w")
    tmp.write("LAN_ENABLED=true\n")
    tmp.close()
    old = auth._CONFIG_PATH
    auth._CONFIG_PATH = tmp.name
    auth._attempts.clear()
    auth._tokens.clear()
    yield
    auth._CONFIG_PATH = old
    os.unlink(tmp.name)


@pytest_asyncio.fixture(scope="function")
async def db_session():
    """Create an in-memory SQLite database with all tables for each test."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()
