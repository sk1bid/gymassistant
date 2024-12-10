# alembic/env.py
import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Загрузка переменных окружения из .env
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

# Импорт моделей
from database.models import Base  # Убедитесь, что путь правильный

# Настройка Alembic Config
config = context.config

# Настройка логирования
fileConfig(config.config_file_name)

# Получение URL базы данных
DATABASE_URL = os.getenv('DB_URL')
if not DATABASE_URL:
    raise ValueError("Переменная окружения DB_URL не установлена.")

# Метаданные для автогенерации
target_metadata = Base.metadata

def run_migrations_offline():
    """Запуск миграций в офлайн-режиме."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection: Connection):
    """Функция для запуска миграций."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online():
    """Запуск миграций в онлайн-режиме."""
    connectable = create_async_engine(
        DATABASE_URL,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()

if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
