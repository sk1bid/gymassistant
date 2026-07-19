"""
Вход в Mini App из чата.

Бот остаётся точкой входа: кнопка меню рядом со скрепкой открывает веб-интерфейс,
а /app присылает ту же кнопку сообщением. Само меню бота (расписание, программы,
профиль) никуда не делось — просто им больше незачем пользоваться.
"""
import logging
import os

from aiogram import Bot, Router, types
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    WebAppInfo,
)

from filters.chat_types import ChatTypeFilter

MINIAPP_URL = os.getenv("MINIAPP_URL", "")

router = Router()
router.message.filter(ChatTypeFilter(["private"]))


@router.message(Command("app"))
async def open_app(message: types.Message):
    if not MINIAPP_URL:
        await message.answer("Mini App не настроен: не задан MINIAPP_URL.")
        return

    await message.answer(
        "💪 <b>GYM.assistant</b>\n\n"
        "Тренировка, программы и история — в приложении.\n"
        "Уведомления об отдыхе придут сюда, в чат.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Открыть приложение", web_app=WebAppInfo(url=MINIAPP_URL)),
        ]]),
    )


async def setup_menu_button(bot: Bot) -> None:
    """
    Вешает Mini App на кнопку меню — ту, что слева от поля ввода.

    Это единственный вызов Telegram API, и он идёт через тот же SOCKS5-прокси,
    что и остальной трафик бота: провайдер режет подсети Telegram напрямую.
    """
    if not MINIAPP_URL:
        logging.warning("MINIAPP_URL не задан — кнопка меню не настроена")
        return

    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text="Тренировка", web_app=WebAppInfo(url=MINIAPP_URL)),
    )
    logging.info("кнопка меню ведёт на %s", MINIAPP_URL)
