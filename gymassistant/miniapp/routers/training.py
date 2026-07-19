"""Тренировочный процесс: старт, запись подходов, правка, завершение."""
import uuid

from fastapi import APIRouter, HTTPException

from database.orm_extra import (
    orm_delete_set,
    orm_finish_training_session,
    orm_get_active_session,
    orm_get_sets_of_session,
    orm_start_rest_timer,
    orm_start_training_session,
    orm_stop_rest_timer,
    orm_update_set,
)
from database.orm_query import orm_add_set, orm_get_exercises, orm_get_program
from miniapp.db import Session
from miniapp.deps import CurrentUser
from miniapp.ownership import own_day, own_exercise, own_set, own_training_session
from miniapp.schemas import FinishTrainingIn, SetEditIn, SetIn, StartTrainingIn
from miniapp.state import DEFAULT_CIRCULAR_ROUNDS, training_state
from services.workout import build_plan, current_step, rest_after

router = APIRouter(prefix="/api/training", tags=["training"])


def parse_session_id(session_id: str) -> uuid.UUID:
    """
    Строка → UUID.

    Колонка объявлена UUID, и на SQLite строка роняет вставку с
    'str' object has no attribute 'hex'. На Postgres она проходила — поэтому баг
    в боте (user_private.py клал туда str(...)) годами никто не замечал.
    """
    try:
        return uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(400, "битый id тренировки")


@router.post("/start")
async def start(body: StartTrainingIn, user: CurrentUser, session: Session):
    """
    Начинает тренировку.

    Если незавершённая по этому дню уже есть — возвращает её, а не заводит вторую:
    две открытые вкладки не должны превращаться в две тренировки.
    """
    day = await own_day(session, user.user_id, body.training_day_id)

    if not await orm_get_exercises(session, day.id):
        raise HTTPException(400, "в этом дне нет упражнений")

    active = await orm_get_active_session(session, user.user_id)
    if active:
        if active.training_day_id == day.id:
            return await training_state(session, user, active)
        # Тренировка по другому дню, брошенная и не закрытая. Двух одновременных
        # тренировок не бывает, а если оставить её висеть, /training/state потом
        # не сможет однозначно сказать, какая из них текущая.
        await orm_finish_training_session(session, active.id)

    started = await orm_start_training_session(session, user.user_id, day.id, note="Mini App")
    return await training_state(session, user, started)


@router.get("/state")
async def state(user: CurrentUser, session: Session):
    """Текущая тренировка, если она идёт. Ею же приложение восстанавливается после закрытия."""
    active = await orm_get_active_session(session, user.user_id)
    if not active:
        return {"ok": True, "session_id": None}
    return await training_state(session, user, active)


@router.post("/set")
async def add_set(body: SetIn, user: CurrentUser, session: Session):
    """
    Записывает подход и сразу ставит таймер отдыха.

    Таймер — строка в БД, дальше его ведёт воркер в процессе бота. Поэтому пинг
    придёт, даже если Mini App закрыт и телефон лежит экраном вниз на скамье, —
    а именно так тренировка и проходит.
    """
    training = await own_training_session(session, user.user_id, parse_session_id(body.session_id))
    exercise = await own_exercise(session, user.user_id, body.exercise_id)

    await orm_add_set(session, {
        "exercise_id": exercise.id,
        "weight": body.weight,
        "repetitions": body.reps,
        "training_session_id": training.id,   # UUID, а не строка — см. parse_session_id
    })

    await _schedule_rest(session, user, training)
    return await training_state(session, user, training)


async def _schedule_rest(session: Session, user: CurrentUser, training):
    """Ставит отдых, положенный после только что закрытого шага."""
    program = await orm_get_program(session, user.actual_program_id) if user.actual_program_id else None
    if not program:
        return

    exercises = await orm_get_exercises(session, training.training_day_id)
    plan = build_plan(exercises, program.circular_rounds or DEFAULT_CIRCULAR_ROUNDS)
    done = await orm_get_sets_of_session(session, training.id)

    following = current_step(plan, done)
    if following is None:
        # Последний подход дня — отдыхать не от чего.
        await orm_stop_rest_timer(session, user.user_id)
        return

    # Подходы записываются в порядке плана, поэтому только что закрыт шаг len(done)-1.
    closed = plan[min(len(done), len(plan)) - 1] if done else None
    if closed is None:
        return

    seconds = rest_after(closed, following, program)
    if seconds <= 0:
        return

    names = {e.id: e.name for e in exercises}
    await orm_start_rest_timer(
        session,
        user_id=user.user_id,
        chat_id=user.user_id,  # приватный чат с ботом: chat_id совпадает с user_id
        seconds=seconds,
        next_up=f"{names.get(following.exercise_id, '')} — подход {following.set_number}",
        quiet=program.quiet_rest_pings,
    )


@router.patch("/set/{set_id}")
async def edit_set(set_id: int, body: SetEditIn, user: CurrentUser, session: Session):
    """Правка уже записанного подхода — промахнуться по степперу проще простого."""
    await own_set(session, user.user_id, set_id)
    await orm_update_set(session, set_id, body.weight, body.reps)
    return await _state_or_ok(session, user)


@router.delete("/set/{set_id}")
async def delete_set(set_id: int, user: CurrentUser, session: Session):
    await own_set(session, user.user_id, set_id)
    await orm_delete_set(session, set_id)
    return await _state_or_ok(session, user)


async def _state_or_ok(session: Session, user: CurrentUser):
    """Подход могли править и из истории, когда никакая тренировка не идёт."""
    active = await orm_get_active_session(session, user.user_id)
    if not active:
        return {"ok": True}
    return await training_state(session, user, active)


@router.post("/finish")
async def finish(body: FinishTrainingIn, user: CurrentUser, session: Session):
    """Завершение — штатное или досрочное; для БД это одно и то же."""
    training = await own_training_session(session, user.user_id, parse_session_id(body.session_id))

    await orm_finish_training_session(session, training.id)
    await orm_stop_rest_timer(session, user.user_id)

    done = await orm_get_sets_of_session(session, training.id)
    return {
        "ok": True,
        "sets": len(done),
        "exercises": len({s.exercise_id for s in done}),
        "volume": sum(s.weight * s.repetitions for s in done),
    }
