"""
Схема базы против моделей.

Почему этот файл вообще появился. 24 теста были зелёными, а профиль на тестовом
контуре отдавал «ошибка сервера»: в моделях и в миграции была колонка `set.skipped`,
а в живой базе её не было. Поймать это было нечем — и не из-за пробела в покрытии,
а по построению:

* схему в тестах поднимает `create_all` ИЗ ТЕХ ЖЕ моделей, поэтому расхождения
  между моделями и тестовой базой не бывает никогда;
* `create_all` создаёт недостающие таблицы, но не добавляет недостающие колонки,
  поэтому на живой базе расхождение как раз бывает — и молча;
* цепочка миграций не умеет построить схему с нуля (см. тест ниже), так что просто
  переключить тесты на alembic нельзя.

Отсюда два разных теста: один проверяет саму цепочку миграций (дёшево, работает
везде), второй сверяет модели с НАСТОЯЩЕЙ базой и включается, только когда она есть.
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

_TMP_DB = Path(tempfile.mkdtemp()) / "schema.db"
os.environ.setdefault("DB_URL", f"sqlite+aiosqlite:///{_TMP_DB}")
os.environ.setdefault("MINIAPP_BOT_TOKEN", "123:TEST")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alembic.config import Config  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402

from database.engine import missing_schema  # noqa: E402
from database.models import Base  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


def _script() -> ScriptDirectory:
    return ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))


# ---------------------------------------------------------------- цепочка миграций


def test_migration_chain_has_exactly_one_head():
    """
    Две головы — это гарантированный «Multiple head revisions» на деплое.

    Ловится параллельными ветками: двое добавили по миграции от одного и того же
    down_revision, оба смёржили, и `alembic upgrade head` встал.
    """
    assert len(_script().get_heads()) == 1


def test_every_migration_on_disk_is_reachable_from_head():
    """
    Ни одна миграция не лежит в стороне от цепочки.

    Осиротевшая ревизия (down_revision указывает на удалённый файл, или её просто
    забыли встроить) физически лежит в versions/, но `upgrade head` до неё не дойдёт —
    и её колонки тихо не появятся. Сравниваем файлы на диске с тем, что реально
    обходится от головы вниз.
    """
    script = _script()

    reachable = {revision.revision for revision in script.walk_revisions()}
    on_disk = {
        line.split("'")[1]
        for path in (ROOT / "alembic" / "versions").glob("*.py")
        for line in path.read_text().splitlines()
        if line.startswith("revision: str")
    }

    assert on_disk - reachable == set(), "миграции есть на диске, но не в цепочке"
    # И цепочка действительно доходит до начала, а не обрывается в середине.
    assert any(revision.down_revision is None for revision in script.walk_revisions())


def test_new_columns_come_with_a_migration():
    """
    Каждая колонка, добавленная моделями, упомянута хоть в одной миграции.

    Именно эта связь и порвалась: `set.skipped` в миграции БЫЛ, но проверить, что
    миграцию накатили, было нечем. Тест грубый — он читает исходники миграций как
    текст, — но ловит ровно то, что нужно: колонку завели в модели и забыли миграцию.

    Колонки из самой первой схемы исключены: она заводилась `create_all`, и
    «начальная миграция» в этом проекте ничего не создаёт (см. следующий тест).
    """
    versions = ROOT / "alembic" / "versions"
    text = "\n".join(f.read_text() for f in versions.glob("*.py"))

    # Что появилось ДО того, как в проекте завели alembic: описано только в моделях,
    # и переписывать историю ради этого никто не будет.
    baseline = {
        "created", "updated", "id", "name", "description", "user_id", "weight",
        "position", "date", "note", "exercise_id", "repetitions", "category_id",
        "image", "admin_exercise_id", "user_exercise_id", "training_day_id",
        "training_program_id", "training_session_id", "day_of_week", "base_sets",
        "base_reps", "actual_program_id", "rest_between_exercise", "rest_between_set",
    }

    # Известный долг: колонки заводились прямо в моделях, миграцию к ним не написали,
    # в живых базах они появились через create_all. Дописывать миграцию задним числом
    # нельзя — на проде и на тесте эти колонки уже есть, и add_column упадёт.
    # Их защищает не этот тест, а сверка с живой базой ниже.
    known_debt = {
        "training_program.circular_rounds",
        "training_program.circular_rest_between_rounds",
        "training_program.circular_rest_between_exercise",
        "exercise_set.reps",
    }

    missing = [
        name
        for table in Base.metadata.sorted_tables
        for column in table.columns
        if (name := f"{table.name}.{column.name}") not in known_debt
        and column.name not in baseline
        and f"'{column.name}'" not in text
    ]

    assert not missing, f"колонки есть в моделях, но их нет ни в одной миграции: {missing}"


def test_migrations_do_not_build_the_core_schema():
    """
    Зафиксированный факт, а не пожелание: цепочка НЕ строит схему с нуля.

    Первая миграция (f42919bf42b1) сгенерирована против уже готовой базы и делает
    единственное — `drop_column('admin_exercises', 'image')`. Таблицы вроде `user`,
    `set` и `training_session` не создаёт ни одна миграция: схему всегда поднимал
    `create_all`, а миграции ложились сверху инкрементами. Отсюда и `alembic stamp`
    перед первым `upgrade` на проде.

    Тест стоит здесь, чтобы это не выяснялось второй раз в бою — и чтобы никто не
    попытался «просто прогнать миграции» на пустой базе, получив полсхемы.
    Если цепочку когда-нибудь починят, тест упадёт и его надо будет заменить на
    честную сверку «upgrade head даёт схему моделей».
    """
    versions = ROOT / "alembic" / "versions"
    text = "\n".join(f.read_text() for f in versions.glob("*.py"))

    never_created = {"user", "exercise", "set", "training_session", "training_program",
                     "training_day", "admin_exercises", "user_exercises"}

    created = {name for name in never_created if f"create_table(\n        '{name}'" in text
               or f"create_table('{name}'" in text}

    assert created == set(), (
        f"миграции научились создавать {created} — возможно, цепочку починили. "
        "Тогда этот тест надо заменить на сверку 'upgrade head' с моделями."
    )


# ---------------------------------------------------------------- живая база


@pytest.mark.anyio
async def test_live_database_has_every_column_the_models_declare():
    """
    Главный тест этого файла: в базе есть всё, что объявляют модели.

    На SQLite он проходит всегда — схему только что построил `create_all` из тех же
    моделей. Смысл появляется, когда DB_URL указывает на настоящую базу:

        DB_URL=postgresql+asyncpg://... ./.venv-bot/bin/pytest tests/test_schema.py -q

    Это и есть проверка «миграции накатили», которой не хватало: она отвечает не
    «совпадают ли файлы», а «переживёт ли приложение деплой».
    """
    from database.engine import engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        problems = await conn.run_sync(missing_schema)

    assert problems == []


@pytest.mark.anyio
async def test_startup_refuses_to_run_on_a_stale_schema():
    """
    Отставшая схема роняет старт, а не первый запрос к профилю.

    Раньше приложение поднималось как ни в чём не бывало, проходило readiness, и
    «ошибка сервера» доставалась пользователю — причём сразу на четырёх экранах,
    потому что недостающая колонка стояла в общем запросе сводки. Воспроизводим
    ровно тот случай: колонка есть в моделях, в базе её нет.
    """
    from sqlalchemy import text

    from database.engine import create_db, engine

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text('ALTER TABLE "set" DROP COLUMN skipped'))

            assert await conn.run_sync(missing_schema) == ["set.skipped"]

        with pytest.raises(RuntimeError, match="set.skipped"):
            await create_db()
    finally:
        # База файловая и общая на весь прогон: колонку надо вернуть в любом случае,
        # иначе испорченная схема утечёт в тесты, которые запустятся следом.
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
