"""
Единые часы приложения.

Два времени, которые нельзя путать:

* ХРАНЕНИЕ и ДЛИТЕЛЬНОСТИ — naive UTC (`utcnow`). Колонки DateTime объявлены без
  таймзоны, а вычитать aware из naive Python не даёт. Для «сколько секунд осталось»
  пояс не важен вовсе — важна одна общая шкала на сервере.

* «СЕГОДНЯ» и локальное время — в зоне ПОЛЬЗОВАТЕЛЯ. Её присылает его телефон
  (`Intl.DateTimeFormat().resolvedOptions().timeZone`) заголовком на каждом запросе.
  На локаль процесса (`date.today()`, `datetime.now()` без tz) не опираемся НИГДЕ:
  сервер стоит в НСК, но пользователь может быть в любом поясе, а сам контейнер
  (python:slim без TZ) вообще живёт в UTC — то есть `date.today()` в поде дало бы
  UTC-дату и ночью по НСК показывало бы вчерашний день.
"""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, available_timezones

# Фолбэк, пока телефон ещё не сообщил зону (самый первый запрос) и для фоновых задач
# без клиента. НСК — где физически стоит сервер и где сейчас большинство юзеров.
DEFAULT_TZ = ZoneInfo("Asia/Novosibirsk")

# available_timezones() читает базу зон с диска — дёргать на каждый запрос дорого,
# берём список один раз при импорте.
_KNOWN = available_timezones()


def utcnow() -> datetime:
    """Naive-UTC «сейчас» — канонические часы для хранения и длительностей."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def resolve_tz(name: str | None) -> ZoneInfo:
    """
    IANA-имя зоны от клиента → ZoneInfo. Мусор или отсутствие → дефолт.

    Заголовок запроса — недоверенный вход, поэтому сверяемся со списком известных
    зон: `ZoneInfo("'; DROP TABLE")` не должен ни падать, ни что-то значить.
    """
    if name and name in _KNOWN:
        return ZoneInfo(name)
    return DEFAULT_TZ


def today_in(tz: ZoneInfo) -> date:
    """Календарная дата «сейчас» в зоне tz — это и есть «сегодня» для пользователя."""
    return datetime.now(tz).date()


def now_in(tz: ZoneInfo) -> datetime:
    """Aware «сейчас» в зоне tz — для локального времени напоминаний (P1)."""
    return datetime.now(tz)
