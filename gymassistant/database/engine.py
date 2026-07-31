
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


def missing_schema(sync_conn) -> list[str]:
    """
    Чего модели ждут от базы, а база этого не имеет.

    Существует потому, что `create_all` создаёт недостающие ТАБЛИЦЫ, но никогда
    не добавляет недостающие КОЛОНКИ. Добавили поле в модель, не накатили миграцию —
    и приложение стартует как ни в чём не бывало, а падает потом, на первом запросе,
    который это поле трогает. Ровно так профиль отдавал «ошибка сервера», когда
    появился `set.skipped`: колонка была в модели и в миграции, но не в базе.

    Тесты такое поймать не могут по построению: они поднимают схему тем же
    `create_all` из тех же моделей, поэтому расхождения там не бывает никогда.
    Сверять модели с настоящей базой можно только на настоящей базе.
    """
    from sqlalchemy import inspect

    from database.models import Base

    inspector = inspect(sync_conn)
    existing = set(inspector.get_table_names())
    problems: list[str] = []

    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            problems.append(f"нет таблицы {table.name}")
            continue

        actual = {column["name"] for column in inspector.get_columns(table.name)}
        problems.extend(
            f"{table.name}.{column.name}"
            for column in table.columns
            if column.name not in actual
        )

    return problems


async def create_db() -> None:

    from database.models import Base
    from database.orm_query import orm_add_banner_description, orm_create_categories
    from database.text_for_db import description_for_info_pages, categories


    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        problems = await conn.run_sync(missing_schema)

    # Падаем на старте, а не на первом запросе к профилю.
    #
    # Полурабочее приложение хуже упавшего: под проходит readiness, кнопка меню
    # открывается, и «ошибка сервера» ловится уже пользователем — причём на экранах,
    # которые к новой колонке отношения не имеют (профиль, история, рекорды и
    # календарь падают все разом, потому что колонка стоит в общем запросе сводки).
    # Здесь же в логе сразу написано, какой колонки не хватает и что делать.
    if problems:
        raise RuntimeError(
            "схема базы отстала от моделей — не хватает: "
            + ", ".join(problems)
            + ". Примените миграции: alembic upgrade head"
        )

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
