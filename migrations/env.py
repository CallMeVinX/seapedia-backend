import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.config import settings
from app.models import Base

target_metadata = Base.metadata
url = settings.DATABASE_URL

def run_migrations_offline() -> None:
    """
    Executes database migrations in 'offline' mode by generating raw SQL scripts instead of executing them directly against the database.
    Crucial for DBA reviews, CI/CD pipeline auditing, and ensuring that schema changes can be safely analyzed before deployment.
    """
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """
    Synchronous wrapper to execute Alembic's migration logic within a provided active database connection.
    Required because Alembic's core migration execution context expects a synchronous environment, bridging the gap from our async engine.
    """
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Initializes a specialized async database engine and establishes a connection specifically for the migration process.
    Ensures that schema changes are safely applied using SQLAlchemy's async driver compatibility layer.
    """
    connectable = create_async_engine(
        url,
        poolclass=pool.NullPool,
        connect_args={
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
        },
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """
    Main entrypoint for applying database schema changes against a live, running database connection.
    Orchestrates the asynchronous event loop setup necessary to drive the async migration workflow.
    """
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
