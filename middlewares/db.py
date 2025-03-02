import logging
import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import async_sessionmaker


class DataBaseSession(BaseMiddleware):
    def __init__(self, session_pool: async_sessionmaker):
        self.session_pool = session_pool

    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any],
    ) -> Any:
        start_time = time.time()  # Начало измерения времени
        async with self.session_pool() as session:
            data['session'] = session
            result = await handler(event, data)
        elapsed_time = time.time() - start_time
        if elapsed_time > 1:
            logging.warning(
                f"Длительная обработка события {event.__class__.__name__} "
                f"от пользователя {event.from_user.id if hasattr(event, 'from_user') else 'N/A'}: "
                f"{elapsed_time:.3f} секунд"
            )
        return result
