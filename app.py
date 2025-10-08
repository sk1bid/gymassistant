import asyncio
import logging
import os
import contextlib

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from dotenv import find_dotenv, load_dotenv


from middlewares.db import DataBaseSession
from database.engine import create_db, drop_db, session_maker
from handlers.user_private import user_private_router
from handlers.admin_private import admin_router
from handlers.user_group import user_group_router
from utils.load_banners import load_banners_from_folder

load_dotenv(find_dotenv())

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("TOKEN")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
PORT = int(os.getenv("PORT", 8080))

WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
bot.my_admins_list = [851690283]

dp = Dispatcher()
dp.include_routers(user_private_router, user_group_router, admin_router)


async def on_startup(bot: Bot):
    logging.info("Бот запускается (webhook)...")

    run_param = False
    if run_param:
        await drop_db()
    await create_db()

    async with session_maker() as session:
        await load_banners_from_folder(bot, session)
    await bot.set_webhook(
        url=WEBHOOK_URL,
        secret_token=WEBHOOK_SECRET,
        drop_pending_updates=True,
        allowed_updates=dp.resolve_used_update_types(),
    )

    for user in bot.my_admins_list:
        with contextlib.suppress(Exception):
            await bot.send_message(user, f"/start")


async def on_shutdown(bot: Bot):
    logging.info("Выключаем вебхук...")
    with contextlib.suppress(Exception):
        await bot.delete_webhook(drop_pending_updates=False)


async def init_app() -> web.Application:

    dp.update.middleware(DataBaseSession(session_pool=session_maker))

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    app = web.Application()

    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET
    ).register(app, path=WEBHOOK_PATH)

    setup_application(app, dp, bot=bot)

    return app


def main():
    app = asyncio.run(init_app())
    web.run_app(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
