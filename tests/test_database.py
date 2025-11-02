"""
Test database configuration that properly handles SQLite.
"""
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool


def create_test_engine(database_url: str = "sqlite+aiosqlite:///:memory:"):
    """Create a test database engine optimized for SQLite."""
    return create_async_engine(
        database_url,
        poolclass=StaticPool,
        connect_args={
            "check_same_thread": False,
        },
        echo=False  # Set to True for SQL debugging
    )