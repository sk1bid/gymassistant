"""Главный экран и расписание."""
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from database.orm_extra import (
    orm_delete_empty_sessions,
    orm_get_active_session,
    orm_get_rest_timer,
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
    """Дни программы в порядке Пн→Вс — в БД они лежат в порядке вставки."""
    days = await orm_get_training_days(session, program_id)
    by_name = {d.day_of_week.strip().lower(): d for d in days}

    out = []
    for name in WEEK_DAYS_RU:
        day = by_name.get(name.lower())
        if not day:
            continue
        exercises = await orm_get_exercises(session, day.id)
        out.append({**day_json(day), "exercises": [exercise_json(e) for e in exercises]})
    return out


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
    if user.actual_program_id:
        days = await week(session, user.actual_program_id)
        today = next((d for d in days if d["day_of_week"].strip().lower() == today_name.lower()), None)

    return {
        "ok": True,
        "user": {"id": user.user_id, "name": user.name, "weight": user.weight},
        "programs": [program_json(p, user.actual_program_id) for p in programs],
        "has_program": bool(user.actual_program_id),
        "today": today,
        "today_name": today_name,
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
