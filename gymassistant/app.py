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


from database.orm_query import orm_get_banner
from middlewares.db import DataBaseSession
from database.engine import create_db, drop_db, session_maker
from handlers.user_private import user_private_router
from handlers.admin_private import admin_router
from handlers.user_group import user_group_router
from utils.load_banners import load_banners_from_folder
from utils import globals

load_dotenv(find_dotenv())

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("TOKEN")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
PORT = int(os.getenv("PORT", 8080))

WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

ADMIN_IDS = [int(id) for id in os.getenv("ADMIN_IDS", "851690283").split(",")]

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
bot.my_admins_list = ADMIN_IDS

dp = Dispatcher()
dp.include_routers(user_private_router, user_group_router, admin_router)


async def on_startup(bot: Bot):
    logging.info("Бот запускается (webhook)...")

    run_param = False
    if run_param:
        await drop_db()
    await create_db()
    async with session_maker() as session:
        globals.error_pic = await orm_get_banner(session, "error")
        
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


async def main():
    dp.update.middleware(DataBaseSession(session_pool=session_maker))

    if os.getenv("USE_POLLING", "False").lower() == "true":
        logging.info("Starting bot in POLLING mode...")
        await bot.delete_webhook(drop_pending_updates=True)
        dp.startup.register(on_startup_polling)
        await dp.start_polling(bot)
    else:
        logging.info("Starting bot in WEBHOOK mode...")
        app = await init_app()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", PORT)
        await site.start()
        # Keep the loop running
        while True:
            await asyncio.sleep(3600)

async def on_startup_polling(bot: Bot):
    logging.info("Бот запускается (polling)...")
    await create_db()
    async with session_maker() as session:
        globals.error_pic = await orm_get_banner(session, "error")
        await load_banners_from_folder(bot, session)
    
    for user in bot.my_admins_list:
        with contextlib.suppress(Exception):
            await bot.send_message(user, "Бот запущен в режиме POLLING")

if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt, SystemExit):
        asyncio.run(main())
