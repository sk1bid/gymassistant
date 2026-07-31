"""
Тесты воркера отдыха.

Bot подменён фейком — Telegram нам тут недоступен и не нужен: проверяем не отправку,
а решения воркера. Главное, что должно быть зафиксировано тестом:

* пинг — это НОВОЕ сообщение с удалением предыдущего, а не редактирование
  (редактирование в Telegram не даёт уведомления, и вся затея теряет смысл);
* КАЖДЫЙ пинг со звуком — тихий режим убран, он отменял смысл уведомления;
* пинги приходят на границах оставшихся минут, а стартового пинга нет;
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


async def advance(db, seconds: int):
    """
    Промотать отдых вперёд, не трогая системные часы.

    Конец придвигается ближе, а прошлый пинг уезжает дальше в прошлое — ровно так,
    как это выглядело бы при настоящем ходе времени. Двигать только `ends_at` нельзя:
    `_should_ping` считает границу минуты между `last_ping` и `ends_at`, и отдых
    «сжался» бы вместо того, чтобы идти.
    """
    timer = await orm_get_rest_timer(db, USER_ID)
    timer.ends_at -= timedelta(seconds=seconds)
    if timer.last_ping:
        timer.last_ping -= timedelta(seconds=seconds)
    await db.commit()
    return timer


@pytest.mark.anyio
async def test_ping_is_a_new_message_not_an_edit(db):
    """
    Каждый пинг удаляет прошлое сообщение и шлёт новое.

    Это не оптимизируется в editMessageText: редактирование не даёт ни пуша, ни
    вибрации, а телефон в этот момент лежит экраном вниз на скамье.
    """
    bot = FakeBot()
    await orm_start_rest_timer(db, USER_ID, USER_ID, seconds=300, next_up="Жим лёжа — подход 2")

    # Прошла минута — первый пинг. Удалять пока нечего.
    await _handle_timer(bot, db, await advance(db, 60))

    assert len(bot.sent) == 1
    assert bot.deleted == []
    assert "Жим лёжа" in bot.sent[0]["text"]
    first_message_id = bot.sent[0]["message_id"]

    # Ещё минута — второй пинг сносит первое сообщение и шлёт новое.
    await _handle_timer(bot, db, await advance(db, 60))

    assert len(bot.sent) == 2
    assert bot.deleted == [first_message_id]


@pytest.mark.anyio
async def test_no_ping_at_the_very_start(db):
    """
    В момент старта отдыха пинга нет.

    Человек только что записал подход и смотрит в приложение, где отсчёт и так идёт;
    сообщать «отдыхайте ещё 5 мин» в ту же секунду незачем. Практическое следствие:
    минутный отдых даёт ровно одно уведомление — «Отдых окончен!».
    """
    bot = FakeBot()
    await orm_start_rest_timer(db, USER_ID, USER_ID, seconds=300)

    await _handle_timer(bot, db, await orm_get_rest_timer(db, USER_ID))
    assert bot.sent == []

    # Минутный отдых: до самого конца — тишина, и только потом «окончен».
    await orm_start_rest_timer(db, USER_ID, USER_ID, seconds=60)
    await _handle_timer(bot, db, await advance(db, 55))
    assert bot.sent == []

    await _handle_timer(bot, db, await advance(db, 5))
    assert len(bot.sent) == 1
    assert "Отдых окончен" in bot.sent[0]["text"]


@pytest.mark.anyio
async def test_every_ping_is_loud(db):
    """
    Звук на КАЖДОМ пинге, включая промежуточные минуты.

    Раньше промежуточные уходили с disable_notification (настройка quiet_rest_pings,
    по умолчанию включённая), и сообщение, ради которого телефон лежит на скамье,
    приходило беззвучно. Тихий режим убран целиком — это регрессионный тест на то,
    что его не вернут.
    """
    bot = FakeBot()
    await orm_start_rest_timer(db, USER_ID, USER_ID, seconds=300)

    for _ in range(4):                                  # 4 мин → 3 → 2 → 1
        await _handle_timer(bot, db, await advance(db, 60))

    assert len(bot.sent) == 4
    assert [m["silent"] for m in bot.sent] == [False] * 4
    assert [m["text"].split("<b>")[1].split("</b>")[0] for m in bot.sent] == ["4", "3", "2", "1"]

    # Время вышло — звонкое «Отдых окончен» и таймер погашен.
    await _handle_timer(bot, db, await advance(db, 60))

    assert "Отдых окончен" in bot.sent[-1]["text"]
    assert bot.sent[-1]["silent"] is False
    assert (await orm_get_rest_timer(db, USER_ID)).active is False


@pytest.mark.anyio
async def test_timer_survives_process_restart(db):
    """
    Баг 1: таймер жил в asyncio-таске с состоянием в FSM (MemoryStorage), и рестарт
    пода тихо убивал отдых. Теперь он лежит в БД: «перезапускаем» процесс — берём
    таймер заново и продолжаем с того же места.
    """
    await orm_start_rest_timer(db, USER_ID, USER_ID, seconds=180, next_up="Присед — подход 3")

    bot = FakeBot()
    await _handle_timer(bot, db, await advance(db, 60))
    assert len(bot.sent) == 1

    # Новый процесс, новый бот, ничего в памяти не осталось.
    restarted = FakeBot()
    timer = await orm_get_rest_timer(db, USER_ID)

    assert timer.active is True
    assert timer.next_up == "Присед — подход 3"
    assert (timer.ends_at - utcnow()).total_seconds() > 0

    # Пингует дальше, сносит сообщение, отправленное ещё до «рестарта».
    await _handle_timer(restarted, db, await advance(db, 60))

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

    await _handle_timer(bot, db, await advance(db, 60))      # пинг отдыха
    await _handle_timer(bot, db, await advance(db, 300))     # время вышло → «окончено»

    done_id = bot.sent[-1]["message_id"]
    assert "Отдых окончен" in bot.sent[-1]["text"]
    timer = await orm_get_rest_timer(db, USER_ID)
    assert timer.active is False
    assert timer.message_id == done_id                       # «окончено» трекается

    # Новый подход → новый отдых. Начало отдыха НЕ обнуляет ссылку на прошлое «окончено».
    await orm_start_rest_timer(db, USER_ID, USER_ID, seconds=300, next_up="Жим — подход 3")
    timer = await orm_get_rest_timer(db, USER_ID)
    assert timer.message_id == done_id

    await _handle_timer(bot, db, await advance(db, 60))      # первый пинг сносит прошлое «окончено»
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

    await _handle_timer(bot, db, await advance(db, 60))
    await _handle_timer(bot, db, await advance(db, 300))      # _finish → «окончено»
    done_id = bot.sent[-1]["message_id"]

    await _sweep_finished(bot, db)                           # свежее — не трогаем
    assert done_id not in bot.deleted

    timer = await orm_get_rest_timer(db, USER_ID)
    timer.last_ping = utcnow() - timedelta(seconds=REST_DONE_TTL + 1)
    await db.commit()
    await _sweep_finished(bot, db)                           # состарилось — сносим
    assert done_id in bot.deleted
    assert (await orm_get_rest_timer(db, USER_ID)).message_id is None


def test_ping_text():
    """Текст всегда в минутах: пинги приходят только на границах минут."""
    assert "5" in _ping_text(300, None)
    assert "Дальше: Жим" in _ping_text(300, "Жим")

    # Округление вверх: 119 секунд человек считает двумя минутами, а не одной.
    # Тик воркера идёт раз в 5 секунд, поэтому граница ловится с недолётом.
    assert "2" in _ping_text(119, None)
    assert "1" in _ping_text(60, None)


def test_ping_schedule_follows_minute_boundaries():
    """
    Решение «пора ли пинговать» — чистая функция от таймера и остатка.

    Раньше отсчёт шёл «60 секунд от прошлого пинга», и сообщения приходили не на
    круглых минутах, а когда придётся.
    """
    now = utcnow()

    class Timer:
        total_seconds = 300
        ends_at = now + timedelta(seconds=300)
        last_ping = None

    timer = Timer()

    # Пинга на старте нет: отсчёт только начался, границу минуты ещё не прошли.
    assert _should_ping(timer, left=300) is False
    assert _should_ping(timer, left=241) is False
    # Граница пройдена — пинг «осталось 4 минуты».
    assert _should_ping(timer, left=240) is True

    # После пинга точкой отсчёта становится он сам.
    timer.last_ping = now + timedelta(seconds=60)   # пинг случился, когда осталось 240
    assert _should_ping(timer, left=200) is False   # всё ещё четвёртая минута
    assert _should_ping(timer, left=180) is True    # третья

    # Минутный отдых: до самого конца ни одного промежуточного пинга.
    class Minute:
        total_seconds = 60
        ends_at = now + timedelta(seconds=60)
        last_ping = None

    assert _should_ping(Minute(), left=60) is False
    assert _should_ping(Minute(), left=30) is False
    assert _should_ping(Minute(), left=1) is False
