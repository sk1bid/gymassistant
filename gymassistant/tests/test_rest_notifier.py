"""
Тесты воркера отдыха.

Bot подменён фейком — Telegram нам тут недоступен и не нужен: проверяем не отправку,
а решения воркера. Главное, что должно быть зафиксировано тестом:

* пинг — это НОВОЕ сообщение с удалением предыдущего, а не редактирование
  (редактирование в Telegram не даёт уведомления, и вся затея теряет смысл);
* промежуточные минуты уходят тихо, конец отдыха — со звуком;
* таймер живёт в БД, поэтому переживает перезапуск процесса.
"""
import os
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

import pytest

_TMP_DB = Path(tempfile.mkdtemp()) / "rest.db"
os.environ["DB_URL"] = f"sqlite+aiosqlite:///{_TMP_DB}"
os.environ.setdefault("MINIAPP_BOT_TOKEN", "123:TEST")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.engine import create_db, engine, session_maker  # noqa: E402
from database.models import Base  # noqa: E402
from database.orm_extra import (  # noqa: E402
    orm_get_rest_timer,
    orm_start_rest_timer,
    orm_stop_rest_timer,
    utcnow,
)
from workers.rest_notifier import _handle_timer, _ping_text, _should_ping  # noqa: E402

USER_ID = 555_000_777


class FakeBot:
    """Записывает, что бот попытался сделать, вместо похода в Telegram."""

    def __init__(self):
        self.sent: list[dict] = []
        self.deleted: list[int] = []
        self._next_id = 100

    async def send_message(self, chat_id, text, reply_markup=None, disable_notification=False):
        self._next_id += 1
        self.sent.append({
            "chat_id": chat_id,
            "text": text,
            "silent": disable_notification,
            "message_id": self._next_id,
        })

        class Sent:
            message_id = self._next_id

        return Sent()

    async def delete_message(self, chat_id, message_id):
        self.deleted.append(message_id)


@pytest.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await create_db()
    async with session_maker() as session:
        yield session


@pytest.mark.anyio
async def test_ping_is_a_new_message_not_an_edit(db):
    """
    Каждый пинг удаляет прошлое сообщение и шлёт новое.

    Это не оптимизируется в editMessageText: редактирование не даёт ни пуша, ни
    вибрации, а телефон в этот момент лежит экраном вниз на скамье.
    """
    bot = FakeBot()
    await orm_start_rest_timer(db, USER_ID, USER_ID, seconds=300, next_up="Жим лёжа — подход 2")

    # Первый пинг: удалять нечего, сообщение уходит.
    timer = await orm_get_rest_timer(db, USER_ID)
    await _handle_timer(bot, db, timer)

    assert len(bot.sent) == 1
    assert bot.deleted == []
    assert "Жим лёжа" in bot.sent[0]["text"]
    first_message_id = bot.sent[0]["message_id"]

    # Прошла минута — второй пинг сносит первое сообщение и шлёт новое.
    timer = await orm_get_rest_timer(db, USER_ID)
    timer.last_ping = utcnow() - timedelta(seconds=61)
    await db.commit()

    await _handle_timer(bot, db, timer)

    assert len(bot.sent) == 2
    assert bot.deleted == [first_message_id]


@pytest.mark.anyio
async def test_intermediate_pings_are_silent_and_the_end_is_not(db):
    """Промежуточные минуты — без звука; за 30 секунд до конца и в конце — со звуком."""
    bot = FakeBot()
    await orm_start_rest_timer(db, USER_ID, USER_ID, seconds=300, quiet=True)

    timer = await orm_get_rest_timer(db, USER_ID)
    await _handle_timer(bot, db, timer)
    assert bot.sent[-1]["silent"] is True          # «отдыхайте ещё 5 мин» — тихо

    # Осталось 20 секунд — предупреждение должно прозвучать.
    timer = await orm_get_rest_timer(db, USER_ID)
    timer.ends_at = utcnow() + timedelta(seconds=20)
    await db.commit()

    await _handle_timer(bot, db, timer)
    assert bot.sent[-1]["silent"] is False
    assert "сек" in bot.sent[-1]["text"]  # под конец счёт идёт на секунды, не на минуты

    # Время вышло — звонкое «Отдых окончен» и таймер погашен.
    timer = await orm_get_rest_timer(db, USER_ID)
    timer.ends_at = utcnow() - timedelta(seconds=1)
    await db.commit()

    await _handle_timer(bot, db, timer)
    assert "Отдых окончен" in bot.sent[-1]["text"]
    assert bot.sent[-1]["silent"] is False

    assert (await orm_get_rest_timer(db, USER_ID)).active is False


@pytest.mark.anyio
async def test_loud_mode_pings_every_minute_with_sound(db):
    """quiet=False — звук на каждом пинге. Это настройка программы."""
    bot = FakeBot()
    await orm_start_rest_timer(db, USER_ID, USER_ID, seconds=300, quiet=False)

    timer = await orm_get_rest_timer(db, USER_ID)
    await _handle_timer(bot, db, timer)

    assert bot.sent[-1]["silent"] is False


@pytest.mark.anyio
async def test_timer_survives_process_restart(db):
    """
    Баг 1: таймер жил в asyncio-таске с состоянием в FSM (MemoryStorage), и рестарт
    пода тихо убивал отдых. Теперь он лежит в БД: «перезапускаем» процесс — берём
    таймер заново и продолжаем с того же места.
    """
    await orm_start_rest_timer(db, USER_ID, USER_ID, seconds=180, next_up="Присед — подход 3")

    bot = FakeBot()
    timer = await orm_get_rest_timer(db, USER_ID)
    await _handle_timer(bot, db, timer)
    assert len(bot.sent) == 1

    # Новый процесс, новый бот, ничего в памяти не осталось.
    restarted = FakeBot()
    timer = await orm_get_rest_timer(db, USER_ID)

    assert timer.active is True
    assert timer.next_up == "Присед — подход 3"
    assert (timer.ends_at - utcnow()).total_seconds() > 0

    # Пингует дальше, сносит сообщение, отправленное ещё до «рестарта».
    timer.last_ping = utcnow() - timedelta(seconds=61)
    await db.commit()
    await _handle_timer(restarted, db, timer)

    assert len(restarted.sent) == 1
    assert restarted.deleted == [bot.sent[0]["message_id"]]


@pytest.mark.anyio
async def test_stopping_from_either_side_kills_the_same_timer(db):
    """Кнопка в Mini App и кнопка в чате гасят одну и ту же строку в таблице."""
    await orm_start_rest_timer(db, USER_ID, USER_ID, seconds=300)
    assert (await orm_get_rest_timer(db, USER_ID)).active is True

    await orm_stop_rest_timer(db, USER_ID)

    timer = await orm_get_rest_timer(db, USER_ID)
    assert timer.active is False

    # Погашенный таймер воркер больше не трогает.
    from database.orm_extra import orm_get_active_rest_timers
    assert await orm_get_active_rest_timers(db) == []


@pytest.mark.anyio
async def test_completion_message_is_tracked_and_cleared_by_next_rest(db):
    """
    «🔔 Отдых окончен!» не копятся: сообщение трекается в строке таймера, и первый
    пинг следующего отдыха его сносит — в чате всегда одно живое сообщение бота.
    Раньше id «окончено» нигде не сохранялся, а начало отдыха обнуляло message_id,
    поэтому оставался мусор — по одному на каждый подход.
    """
    bot = FakeBot()
    await orm_start_rest_timer(db, USER_ID, USER_ID, seconds=300, next_up="Жим — подход 2")

    timer = await orm_get_rest_timer(db, USER_ID)
    await _handle_timer(bot, db, timer)                      # пинг отдыха

    timer = await orm_get_rest_timer(db, USER_ID)
    timer.ends_at = utcnow() - timedelta(seconds=1)
    await db.commit()
    await _handle_timer(bot, db, timer)                      # ведёт в _finish → «окончено»

    done_id = bot.sent[-1]["message_id"]
    assert "Отдых окончен" in bot.sent[-1]["text"]
    timer = await orm_get_rest_timer(db, USER_ID)
    assert timer.active is False
    assert timer.message_id == done_id                       # «окончено» трекается

    # Новый подход → новый отдых. Начало отдыха НЕ обнуляет ссылку на прошлое «окончено».
    await orm_start_rest_timer(db, USER_ID, USER_ID, seconds=300, next_up="Жим — подход 3")
    timer = await orm_get_rest_timer(db, USER_ID)
    assert timer.message_id == done_id

    await _handle_timer(bot, db, timer)                      # первый пинг сносит прошлое «окончено»
    assert done_id in bot.deleted


@pytest.mark.anyio
async def test_final_completion_is_swept_after_ttl(db):
    """
    Последнее «Отдых окончен!» (тренировка закончилась, следующего отдыха не будет)
    убирает sweep по TTL: свежее не трогает — пуш ещё актуален, старое сносит.
    """
    from workers.rest_notifier import REST_DONE_TTL, _sweep_finished

    bot = FakeBot()
    await orm_start_rest_timer(db, USER_ID, USER_ID, seconds=300)
    timer = await orm_get_rest_timer(db, USER_ID)
    await _handle_timer(bot, db, timer)

    timer = await orm_get_rest_timer(db, USER_ID)
    timer.ends_at = utcnow() - timedelta(seconds=1)
    await db.commit()
    await _handle_timer(bot, db, timer)                      # _finish → «окончено»
    done_id = bot.sent[-1]["message_id"]

    await _sweep_finished(bot, db)                           # свежее — не трогаем
    assert done_id not in bot.deleted

    timer = await orm_get_rest_timer(db, USER_ID)
    timer.last_ping = utcnow() - timedelta(seconds=REST_DONE_TTL + 1)
    await db.commit()
    await _sweep_finished(bot, db)                           # состарилось — сносим
    assert done_id in bot.deleted
    assert (await orm_get_rest_timer(db, USER_ID)).message_id is None


def test_ping_text_and_schedule():
    """Тексты и решение «пора ли пинговать» — чистые функции, проверяем напрямую."""
    assert "5" in _ping_text(300, None)
    assert "Дальше: Жим" in _ping_text(300, "Жим")
    assert "сек" in _ping_text(20, None)          # под конец считаем в секундах

    class Timer:
        last_ping = None
        warned = False

    timer = Timer()
    assert _should_ping(timer, left=300) is True   # первый пинг — сразу

    timer.last_ping = utcnow()
    assert _should_ping(timer, left=300) is False  # минута ещё не прошла
    assert _should_ping(timer, left=20) is True    # но до конца 20 секунд — предупреждаем

    timer.warned = True
    assert _should_ping(timer, left=20) is False   # предупредили один раз, хватит

    timer.last_ping = utcnow() - timedelta(seconds=61)
    assert _should_ping(timer, left=300) is True   # минута прошла
