import asyncio
import os
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from dotenv import find_dotenv, load_dotenv

from database.orm_query import initialize_all_positions

load_dotenv(find_dotenv())

from middlewares.db import DataBaseSession
from database.engine import create_db, drop_db, session_maker
from handlers.user_private import user_private_router
from handlers.admin_private import admin_router
from handlers.user_group import user_group_router

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,  # Уровень логирования, можно изменить на DEBUG для более подробных логов
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # Формат сообщений
    handlers=[
        logging.StreamHandler()  # Вывод логов в консоль
    ]
)

# Подавляем лишние логи от SQLAlchemy и aiogram
logging.getLogger('sqlalchemy.engine').setLevel(logging.ERROR)
logging.getLogger('aiogram').setLevel(logging.ERROR)

# Создаём экземпляр бота
bot = Bot(token=os.getenv('TOKEN'), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
bot.my_admins_list = [851690283]

# Создаём диспетчер и регистрируем роутеры
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
    # Если run_param True, сбрасываем базу данных
    run_param = False
    if run_param:
        await drop_db()

    # Создаём базу данных и инициализируем позиции
    await create_db()
    async with session_maker() as session:
        await initialize_all_positions(session)
        logging.info("Инициализация значений position завершена.")


async def on_shutdown(bot: Bot):
    logging.info('Бот остановлен')


async def main():
    # Регистрируем функции, которые будут выполняться при старте и остановке бота
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Регистрируем middleware для работы с базой данных
    dp.update.middleware(DataBaseSession(session_pool=session_maker))

    # Удаляем вебхук (если он был установлен) и начинаем polling
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logging.error(f"Ошибка при удалении вебхука: {e}")

    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == '__main__':
    asyncio.run(main())
