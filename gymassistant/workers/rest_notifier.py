"""
Пинги отдыха в чат.

Зачем это вообще нужно, если есть Mini App: Mini App не может уведомлять. Закрытая
страница не существует, JS-таймер вместе с ней останавливается, а Web Push внутри
телеграмовского вебвью нет. Между тем вся ценность продукта в том, что телефон лежит
на скамье экраном вниз и пингует, когда отдых кончился. Уведомлять умеет только бот.

Отсюда гибрид: Mini App записывает подходы и рисует живой отсчёт, пока открыт, а
таймер лежит в БД (таблица rest_timer), и ведёт его этот воркер в процессе бота.
Поставить таймер может любой из двух — это просто строка в таблице.

Два принципиальных момента, которые нельзя «оптимизировать»:

1. Каждый пинг — НОВОЕ сообщение с удалением предыдущего, а не editMessageText.
   Редактирование сообщения в Telegram не даёт ни пуша, ни вибрации. Стоит заменить
   это на edit — и уведомления исчезнут, а с ними и смысл всей затеи.

2. Таймер живёт в БД, а не в памяти. Раньше он крутился в asyncio-таске с состоянием
   в FSM (MemoryStorage), и рестарт пода тихо убивал отдых на середине.

Все пинги звонкие. Раньше промежуточные минуты уходили с disable_notification (флаг
`quiet_rest_pings` в настройках программы, по умолчанию включённый) — то есть ровно
то сообщение, ради которого телефон лежит на скамье, приходило беззвучно, и человек
узнавал об окончании отдыха, только заглянув в чат.
"""
import asyncio
import logging
import math
from datetime import timedelta

from aiogram import Bot, F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.types import ReplyKeyboardRemove

from database.orm_extra import (
    orm_clear_rest_message,
    orm_finish_rest_timer,
    orm_get_active_rest_timers,
    orm_get_stale_rest_messages,
    orm_save_rest_ping,
    orm_stop_rest_timer,
    utcnow,
)
from kbds.reply import get_keyboard

REST_END_BUTTON = "🏄‍♂️ Закончить отдых"

# Как часто воркер просыпается. Пинги — раз в минуту, но окончание отдыха надо
# ловить точнее, чем с минутной погрешностью.
TICK_SECONDS = 5
# Сколько «🔔 Отдых окончен!» висит в чате, если следующего отдыха уже не будет
# (конец тренировки). Пуш к этому моменту давно пришёл — дальше это просто мусор.
REST_DONE_TTL = 180

router = Router()


# ---------------------------------------------------------------- кнопка

# StateFilter(None) — только вне FSM: тренировку, запущенную из самого бота, ведёт
# его собственный обработчик отдыха в handlers/user_private.py, и мешать ему не надо.
@router.message(StateFilter(None), F.text == REST_END_BUTTON)
async def end_rest(message: types.Message, session):
    """«Закончить отдых» из чата. Гасит тот же таймер, что и кнопка в Mini App."""
    await orm_stop_rest_timer(session, message.from_user.id)

    await _delete_quietly(message.bot, message.chat.id, message.message_id)
    done = await message.answer("Отдых закончен, работаем 💪", reply_markup=ReplyKeyboardRemove())

    # Убрать подтверждение через пять секунд — но не ожиданием прямо здесь: пока
    # обработчик не вернётся, за ним держится сессия БД из пула.
    _background(_delete_later(message.bot, message.chat.id, done.message_id, delay=5))


# Сильные ссылки на фоновые таски: иначе сборщик мусора вправе убить их на полпути.
_tasks: set[asyncio.Task] = set()


def _background(coro) -> None:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _delete_later(bot: Bot, chat_id: int, message_id: int, delay: int) -> None:
    await asyncio.sleep(delay)
    await _delete_quietly(bot, chat_id, message_id)


# ---------------------------------------------------------------- воркер

async def rest_notifier(bot: Bot, session_maker) -> None:
    """
    Вечный цикл: раз в несколько секунд разбирает активные таймеры.

    Одна упавшая отправка не должна ронять цикл — иначе один пользователь с
    заблокированным ботом лишит уведомлений всех остальных.
    """
    logging.info("воркер отдыха запущен")

    while True:
        try:
            async with session_maker() as session:
                for timer in await orm_get_active_rest_timers(session):
                    try:
                        await _handle_timer(bot, session, timer)
                    except Exception:
                        logging.exception("таймер отдыха user_id=%s: сбой", timer.user_id)

                await _sweep_finished(bot, session)
        except Exception:
            logging.exception("воркер отдыха: сбой итерации")

        await asyncio.sleep(TICK_SECONDS)


async def _sweep_finished(bot: Bot, session) -> None:
    """Убирает зависшие сообщения завершённых таймеров — чтобы чат не копил «окончено»."""
    cutoff = utcnow() - timedelta(seconds=REST_DONE_TTL)
    for timer in await orm_get_stale_rest_messages(session, cutoff):
        await _delete_quietly(bot, timer.chat_id, timer.message_id)
        await orm_clear_rest_message(session, timer.id)


async def _handle_timer(bot: Bot, session, timer) -> None:
    left = int((timer.ends_at - utcnow()).total_seconds())

    if left <= 0:
        await _finish(bot, session, timer)
        return

    if not _should_ping(timer, left):
        return

    await _delete_quietly(bot, timer.chat_id, timer.message_id)

    sent = await bot.send_message(
        timer.chat_id,
        _ping_text(left, timer.next_up),
        reply_markup=get_keyboard(REST_END_BUTTON),
    )
    await orm_save_rest_ping(session, timer.id, sent.message_id)


def _minutes_left(seconds: float) -> int:
    """Сколько минут отдыха человек ещё считает оставшимися: 119 секунд — это «2 мин»."""
    return math.ceil(max(0, seconds) / 60)


def _should_ping(timer, left: int) -> bool:
    """
    Пинг на каждой пройденной границе минуты — и только на ней.

    Раньше отсчёт шёл «60 секунд от прошлого пинга», и текст плыл: сообщения
    приходили не на круглых минутах, а когда придётся, из-за чего под конец
    «осталась 1 минута» и предупреждение за 30 секунд шли почти подряд.

    Стартового пинга нет: в этот момент человек только что записал подход и смотрит
    в приложение, где отсчёт и так идёт. Для минутного отдыха это значит ровно одно
    уведомление — «Отдых окончен!», и это правильно: сообщать «отдыхайте ещё 1 мин»
    в ту же секунду, когда отдых начался, незачем.

    Точка отсчёта — прошлый пинг, а если его не было, начало отдыха. Пропущенные
    границы (воркер лежал, под перезапускался) не догоняются: шлём одно сообщение
    с актуальным остатком.
    """
    reference = timer.last_ping or (timer.ends_at - timedelta(seconds=timer.total_seconds))
    was = (timer.ends_at - reference).total_seconds()

    return _minutes_left(left) < _minutes_left(was)


def _ping_text(left: int, next_up: str | None) -> str:
    head = f"Отдыхайте ещё <b>{_minutes_left(left)}</b> мин."
    return f"{head}\n\nДальше: {next_up}" if next_up else head


async def _finish(bot: Bot, session, timer) -> None:
    """Отдых кончился: гасим таймер и звонко сообщаем об этом."""
    await _delete_quietly(bot, timer.chat_id, timer.message_id)

    text = "🔔 Отдых окончен!"
    if timer.next_up:
        text += f"\n\nДальше: <b>{timer.next_up}</b>"

    # Здесь звук нужен всегда, даже в тихом режиме: ради этого сообщения всё и затевалось.
    sent = await bot.send_message(timer.chat_id, text, reply_markup=ReplyKeyboardRemove())

    # Запоминаем это сообщение как единственное живое сообщение таймера: следующий
    # отдых сотрёт его первым пингом, а конец тренировки — sweep по TTL. Без этого
    # «Отдых окончен!» копились бы в чате по одному на каждый подход.
    await orm_save_rest_ping(session, timer.id, sent.message_id)
    await orm_finish_rest_timer(session, timer.id)


async def _delete_quietly(bot: Bot, chat_id: int, message_id: int | None) -> None:
    """Сообщение мог удалить и сам пользователь — это не ошибка."""
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramBadRequest as e:
        if "message to delete not found" not in str(e):
            logging.warning("не удалось удалить сообщение %s: %s", message_id, e)
