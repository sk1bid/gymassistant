"""
Проверки владения.

Подпись initData доказывает, *кто* пришёл, но не то, что запрошенный объект — его.
Все id приезжают с фронта, и без этих проверок чужую программу можно было бы
прочитать и переписать, просто перебирая числа в URL. Поэтому любой роут, который
принимает id, сначала прогоняет его через функцию отсюда.

Всё отвечает 404, а не 403: существование чужого объекта — тоже информация.
"""
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database.orm_query import (
    orm_get_exercise,
    orm_get_program,
    orm_get_set,
    orm_get_training_day,
    orm_get_training_session,
    orm_get_user_exercise,
)


async def own_program(session: AsyncSession, user_id: int, program_id: int):
    program = await orm_get_program(session, program_id)
    if not program or program.user_id != user_id:
        raise HTTPException(404, "программа не найдена")
    return program


async def own_day(session: AsyncSession, user_id: int, day_id: int):
    day = await orm_get_training_day(session, day_id)
    if not day:
        raise HTTPException(404, "день не найден")
    await own_program(session, user_id, day.training_program_id)
    return day


async def own_exercise(session: AsyncSession, user_id: int, exercise_id: int):
    """Упражнение принадлежит дню, день — программе, программа — пользователю."""
    exercise = await orm_get_exercise(session, exercise_id)
    if not exercise:
        raise HTTPException(404, "упражнение не найдено")
    await own_day(session, user_id, exercise.training_day_id)
    return exercise


async def own_user_exercise(session: AsyncSession, user_id: int, user_exercise_id: int):
    exercise = await orm_get_user_exercise(session, user_exercise_id)
    if not exercise or exercise.user_id != user_id:
        raise HTTPException(404, "упражнение не найдено")
    return exercise


async def own_training_session(session: AsyncSession, user_id: int, session_id):
    """session_id — UUID; строку сюда передавать нельзя, разбирает вызывающий."""
    training_session = await orm_get_training_session(session, session_id)
    if not training_session or training_session.user_id != user_id:
        raise HTTPException(404, "тренировка не найдена")
    return training_session


async def own_set(session: AsyncSession, user_id: int, set_id: int):
    recorded = await orm_get_set(session, set_id)
    if not recorded:
        raise HTTPException(404, "подход не найден")
    await own_training_session(session, user_id, recorded.training_session_id)
    return recorded
