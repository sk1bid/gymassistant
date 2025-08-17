
import os
import logging
from typing import Iterable

from dotenv import load_dotenv, find_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


load_dotenv(find_dotenv())

log = logging.getLogger(__name__)


DB_URL = os.getenv("DB_URL")
DB_ECHO = os.getenv("DB_ECHO", "0") == "1"
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))


if not DB_URL or DB_URL.strip() == "":
    DB_URL = "sqlite+aiosqlite:///./db.sqlite3"
    log.warning(
        "DB_URL не задан, используем fallback: %s\n"
        "Добавьте в .env, например:\n"
        "  DB_URL=postgresql+asyncpg://USER:PASSWORD@localhost:5432/DBNAME",
        DB_URL,
    )


engine_kwargs = {
    "echo": DB_ECHO,
    "pool_pre_ping": True,   # полезно для долгоживущих соединений
}

if DB_URL.startswith("sqlite+aiosqlite"):

    engine_kwargs["poolclass"] = NullPool
else:

    engine_kwargs["pool_size"] = POOL_SIZE
    engine_kwargs["max_overflow"] = MAX_OVERFLOW


engine = create_async_engine(DB_URL, **engine_kwargs)


session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def create_db() -> None:

    from database.models import Base
    from database.orm_query import orm_add_banner_description, orm_create_categories
    from database.text_for_db import description_for_info_pages, categories

 
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

 
    async with session_maker() as session:
        await orm_create_categories(session, categories)
        await orm_add_banner_description(session, description_for_info_pages)


async def drop_db(
    tables_to_exclude: Iterable[str] = ("admin_exercises", "banner", "exercise_category"),
) -> None:


    from database.models import Base

    async with engine.begin() as conn:
        metadata = Base.metadata

   
        tables_to_drop = [t for t in metadata.sorted_tables if t.name not in set(tables_to_exclude)]

        if tables_to_drop:
  
            await conn.run_sync(
                lambda sync_conn: metadata.drop_all(bind=sync_conn, tables=tables_to_drop)
            )
        else:
            log.info("Нет таблиц для удаления — все находятся в списке исключений.")
