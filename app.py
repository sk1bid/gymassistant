import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

from middlewares.db import DataBaseSession
from database.engine import create_db, drop_db, session_maker
from handlers.user_private import user_private_router
from handlers.admin_private import admin_router
from handlers.user_group import user_group_router

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logging.getLogger('sqlalchemy.engine').setLevel(logging.ERROR)
logging.getLogger('aiogram').setLevel(logging.ERROR)

bot = Bot(token=os.getenv('TOKEN'), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
bot.my_admins_list = [851690283]

dp = Dispatcher()
dp.include_routers(user_private_router, user_group_router, admin_router)

engine = session_maker.kw['bind']


async def on_startup(bot: Bot):
    logging.info("Бот запускается...")
    for user in bot.my_admins_list:
        try:
            await bot.send_message(user, 'Бот запущен, пора тестировать')
            await bot.send_message(user, '/start')
        except Exception as e:
            logging.error(f"Не удалось отправить сообщение админу {user}: {e}")
    run_param = False
    if run_param:
        await drop_db()

    await create_db()


async def on_shutdown(bot: Bot):
    logging.info('Бот остановлен')


async def main():
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    dp.update.middleware(DataBaseSession(session_pool=session_maker))

    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logging.error(f"Ошибка при удалении вебхука: {e}")

    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == '__main__':
    asyncio.run(main())
