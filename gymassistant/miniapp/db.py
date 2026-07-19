"""Сессия БД на запрос. Движок — тот же, что у бота, ничего своего."""
from typing import Annotated, AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database.engine import session_maker


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_maker() as session:
        yield session


Session = Annotated[AsyncSession, Depends(get_session)]
