"""Пользователь текущего запроса."""
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, Header

from database.models import User
from database.orm_query import orm_add_user, orm_get_user_by_id
from miniapp.auth import TgUser
from miniapp.config import MAX_USER_NAME
from miniapp.db import Session
from services.clock import resolve_tz


async def get_current_user(tg: TgUser, session: Session) -> User:
    """
    Пользователь из БД, заведённый при первом входе.

    Регистрации как отдельного шага больше нет: имя приезжает в initData, вес
    ставим дефолтный и предлагаем поправить в профиле. Диалог «/start → имя → вес»
    в чате был нужен только потому, что другого способа спросить у бота не было.
    """
    user = await orm_get_user_by_id(session, tg["id"])
    if user:
        return user

    await orm_add_user(session, {
        "user_id": tg["id"],
        "name": (tg.get("first_name") or "Атлет")[:MAX_USER_NAME],
        "weight": 75.0,
    })
    return await orm_get_user_by_id(session, tg["id"])


CurrentUser = Annotated[User, Depends(get_current_user)]


def client_tz(x_timezone: str | None = Header(default=None)) -> ZoneInfo:
    """
    Часовой пояс пользователя из заголовка X-Timezone.

    Его шлёт фронт (Intl.DateTimeFormat) на каждом запросе — так «сегодня» считается
    в поясе конкретного юзера, а не сервера. Невалидное/пустое значение → дефолт.
    Персистить в User (для воркера напоминаний, который без запроса клиента) будем
    в P1 — заголовок для этого уже готов.
    """
    return resolve_tz(x_timezone)


ClientTz = Annotated[ZoneInfo, Depends(client_tz)]
