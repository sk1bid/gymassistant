"""
Отдых.

Таймер один на бота и на Mini App — это строка в таблице rest_timer. Mini App
рисует по нему живой отсчёт, пока открыт; пинги в чат шлёт воркер бота. Кнопка
«Закончить отдых» в любом из двух гасит один и тот же таймер.
"""
from fastapi import APIRouter

from database.orm_extra import orm_get_rest_timer, orm_start_rest_timer, orm_stop_rest_timer
from database.orm_query import orm_get_program
from miniapp.db import Session
from miniapp.deps import CurrentUser
from miniapp.schemas import RestIn
from miniapp.serializers import rest_json

router = APIRouter(prefix="/api/rest", tags=["rest"])


@router.get("")
async def get_rest(user: CurrentUser, session: Session):
    timer = await orm_get_rest_timer(session, user.user_id)
    return {"ok": True, "rest": rest_json(timer)}


@router.post("/start")
async def start_rest(body: RestIn, user: CurrentUser, session: Session):
    """Отдых руками: продлить, когда к стойке очередь, или отдохнуть вне тренировки."""
    program = await orm_get_program(session, user.actual_program_id) if user.actual_program_id else None

    timer = await orm_start_rest_timer(
        session,
        user_id=user.user_id,
        chat_id=user.user_id,
        seconds=body.seconds,
        next_up=body.next_up,
        quiet=program.quiet_rest_pings if program else True,
    )
    return {"ok": True, "rest": rest_json(timer)}


@router.post("/stop")
async def stop_rest(user: CurrentUser, session: Session):
    await orm_stop_rest_timer(session, user.user_id)
    return {"ok": True, "rest": None}
