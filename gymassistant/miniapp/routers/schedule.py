"""Главный экран и расписание."""
from datetime import date, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from database.orm_extra import (
    orm_delete_empty_sessions,
    orm_get_active_session,
    orm_get_exercises_of_days,
    orm_get_rest_timer,
    orm_get_sessions_summary,
    orm_get_trained_day_ids,
    utcnow,
)
from database.orm_query import (
    orm_get_exercises,
    orm_get_program,
    orm_get_programs,
    orm_get_training_days,
)
from miniapp.config import WEEK_DAYS_RU
from miniapp.db import Session
from miniapp.deps import ClientTz, CurrentUser
from miniapp.ownership import own_day
from miniapp.serializers import day_json, exercise_json, program_json, rest_json
from services.clock import today_in

router = APIRouter(prefix="/api", tags=["schedule"])


def today_ru(tz: ZoneInfo) -> str:
    """День недели «сегодня» в поясе пользователя, а не сервера."""
    return WEEK_DAYS_RU[today_in(tz).weekday()]


async def week(session: Session, program_id: int) -> list[dict]:
    """
    Дни программы в порядке Пн→Вс — в БД они лежат в порядке вставки.

    Упражнения всех семи дней забираются одним запросом. Раньше здесь был вызов
    orm_get_exercises внутри цикла: семь последовательных обращений к постгресу
    на каждое открытие главной и расписания, и их задержки складывались — экран
    заметно «думал» перед появлением.
    """
    days = await orm_get_training_days(session, program_id)
    by_name = {d.day_of_week.strip().lower(): d for d in days}

    ordered = [by_name[name.lower()] for name in WEEK_DAYS_RU if name.lower() in by_name]
    exercises = await orm_get_exercises_of_days(session, [d.id for d in ordered])

    return [
        {**day_json(day), "exercises": [exercise_json(e) for e in exercises.get(day.id, [])]}
        for day in ordered
    ]


async def missed_day(session: Session, user, tz, days: list[dict]) -> dict | None:
    """
    Последний пропущенный тренировочный день, если он есть.

    Пропуск — это день программы с упражнениями, чей день недели уже прошёл, а
    тренировки по нему за последнюю неделю не было. Отдаём ОДИН день, самый свежий,
    а не список: пять строк «пропущено» на главной были бы упрёком, а не помощью.

    Три границы, каждая по своей причине.

    **Сравниваем дни ПРОГРАММЫ, а не даты.** Отработал понедельник во вторник —
    это перенос, и в среду напоминать не о чем: сессия помнит `training_day_id`,
    и день считается закрытым независимо от того, какого числа его закрыли.

    **Свежесть — неделя.** Окно стоит на выборке тренировок: то, что делалось
    больше семи суток назад, день уже не закрывает. Иначе тренировка месячной
    давности вечно гасила бы напоминание о том же дне недели.

    **Ищем шесть дней назад, а не семь.** Седьмой — это тот же день недели, что
    сегодня, то есть СЕГОДНЯШНЯЯ тренировка. Предлагать «отработать» то, что и так
    стоит в плане на сегодня, бессмысленно: экран показал бы один и тот же день
    дважды, и обе кнопки открыли бы одну и ту же тренировку. Заодно это и есть
    правило «пропущенное должно идти строго ПЕРЕД тем, что будет»: при поиске на
    шесть дней у дня всегда остаётся хотя бы сутки до его собственного повтора.
    """
    planned = {d["day_of_week"].strip().lower(): d for d in days if d["exercises"]}
    if not planned:
        return None

    today = today_in(tz)
    trained = await orm_get_trained_day_ids(session, user.user_id, utcnow() - timedelta(days=7))

    for back in range(1, 7):
        past = today - timedelta(days=back)
        day = planned.get(WEEK_DAYS_RU[past.weekday()].lower())
        if day and day["id"] not in trained:
            return {"id": day["id"], "day_of_week": day["day_of_week"], "days_ago": back}

    return None


async def weekly_progress(session: Session, user, tz: ZoneInfo, days: list[dict]) -> dict:
    """
    Прогресс недели и серия — мотивационная сводка для главного экрана.

    «Сделано» — сколько РАЗНЫХ дней текущей календарной недели (Пн→сегодня) были
    тренировочными; «цель» — сколько тренировочных дней в программе. Серия — сколько
    недель подряд была хотя бы одна тренировка.

    `left` — сколько тренировочных дней ПРОГРАММЫ на этой неделе ещё впереди
    (сегодняшний считается, пока не отработан). Без него экран обещал невозможное:
    в пятницу при цели 4 и нуле сделанных он писал «ещё 4 тренировки», хотя до
    воскресенья таких дней в программе оставалось разве что один. Разница между
    «сколько не хватает до цели» и «сколько ещё физически влезет» — и есть повод
    считать это на сервере, а не вычитать на клиенте.

    Серия считается мягко: текущая неделя не рвёт её, пока не кончилась. Если на этой
    неделе тренировок ещё нет, отсчёт начинается с прошлой недели (грейс) — иначе
    серия обнулялась бы каждый понедельник, а пропуск дня в зале бывает по делу
    (болезнь, разгрузка), и наказывать за него сбросом цепочки — демотивирует.
    Так же устроены недельные серии у Apple Fitness+ и цель «N дней в неделю»
    у Fitbit: неделя календарная, Пн→Вс, а не скользящее окно.

    Дата тренировки хранится в naive-UTC, а неделя раскладывается по КАЛЕНДАРЮ
    пользователя: тренировка в 6 утра по Новосибирску — это 23:00 UTC накануне,
    и без перевода в пояс часть тренировок села бы в соседнюю неделю.
    """
    rows = await orm_get_sessions_summary(session, user.user_id, limit=400)

    trained: set[date] = set()
    for row in rows:
        if row.date:
            trained.add(row.date.replace(tzinfo=timezone.utc).astimezone(tz).date())

    today = today_in(tz)
    week_start = today - timedelta(days=today.weekday())
    this_week = {day for day in trained if week_start <= day <= today}

    # Дни недели программы, в которых есть упражнения. Имя дня сверяем нормализованным:
    # в базе оно лежит как ввёл пользователь, регистр и пробелы бывают любыми.
    order = {name.lower(): index for index, name in enumerate(WEEK_DAYS_RU)}
    planned = {
        order[day["day_of_week"].strip().lower()]
        for day in days
        if day["exercises"] and day["day_of_week"].strip().lower() in order
    }

    left = sum(1 for weekday in planned if weekday > today.weekday())
    if today.weekday() in planned and today not in this_week:
        left += 1

    weeks_with = {day - timedelta(days=day.weekday()) for day in trained}
    anchor = week_start if week_start in weeks_with else week_start - timedelta(days=7)
    streak = 0
    while anchor in weeks_with:
        streak += 1
        anchor -= timedelta(days=7)

    return {"done": len(this_week), "goal": len(planned), "streak": streak, "left": left}


@router.get("/bootstrap")
async def bootstrap(user: CurrentUser, session: Session, tz: ClientTz):
    """Всё, что нужно приложению при открытии, одним запросом."""
    # Тренировки, начатые и брошенные без единого подхода, только мусорят историю.
    await orm_delete_empty_sessions(session, user.user_id)

    programs = await orm_get_programs(session, user.user_id)
    active = await orm_get_active_session(session, user.user_id)
    timer = await orm_get_rest_timer(session, user.user_id)

    today_name = today_ru(tz)
    today = None
    missed = None
    week_progress = None
    if user.actual_program_id:
        days = await week(session, user.actual_program_id)
        today = next((d for d in days if d["day_of_week"].strip().lower() == today_name.lower()), None)
        missed = await missed_day(session, user, tz, days)
        week_progress = await weekly_progress(session, user, tz, days)

    return {
        "ok": True,
        "user": {"id": user.user_id, "name": user.name, "weight": user.weight},
        "programs": [program_json(p, user.actual_program_id) for p in programs],
        "has_program": bool(user.actual_program_id),
        "today": today,
        "today_name": today_name,
        "missed": missed,
        "week": week_progress,
        "active_session": str(active.id) if active else None,
        "rest": rest_json(timer),
    }


@router.get("/schedule")
async def schedule(user: CurrentUser, session: Session, tz: ClientTz):
    """Неделя активной программы."""
    if not user.actual_program_id:
        return {"ok": True, "program": None, "days": [], "today": today_ru(tz)}

    program = await orm_get_program(session, user.actual_program_id)
    return {
        "ok": True,
        "program": program_json(program, user.actual_program_id),
        "today": today_ru(tz),
        "days": await week(session, program.id),
    }


@router.get("/day/{day_id}")
async def day(day_id: int, user: CurrentUser, session: Session):
    training_day = await own_day(session, user.user_id, day_id)
    exercises = await orm_get_exercises(session, training_day.id)
    return {
        "ok": True,
        "day": day_json(training_day),
        "exercises": [exercise_json(e) for e in exercises],
    }
