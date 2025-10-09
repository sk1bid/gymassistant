from aiogram.types import FSInputFile
import os
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from database.orm_query import orm_change_banner_image



async def load_banners_from_folder(bot, session: AsyncSession):
    folder = "banners"
    if not os.path.exists(folder):
        logging.warning(f"Папка {folder} не найдена, пропускаем загрузку баннеров.")
        return

    banners = [f for f in os.listdir(folder) if f.lower().endswith((".jpg", ".jpeg", ".png"))]
    if not banners:
        logging.info("Нет баннеров для загрузки.")
        return

    for filename in banners:
        path = os.path.join(folder, filename)
        name, _ = os.path.splitext(filename)
        logging.info(f"Загружаем баннер: {filename}")

        try:
            img = FSInputFile(path)

            msg = await bot.send_photo(
                chat_id=bot.my_admins_list[0],
                photo=img,
                caption=f"Загружен баннер: <b>{name}</b>"
            )

            file_id = msg.photo[-1].file_id

            await orm_change_banner_image(session, name, file_id)
            logging.info(f"Баннер {name} обновлён в базе (file_id={file_id[:15]}...).")

        except Exception as e:
            logging.exception(f"Ошибка при загрузке баннера {filename}: {e}")
            await bot.send_message(
                chat_id=bot.my_admins_list[0],
                text=f"⚠️ Ошибка при загрузке {filename}: {e}"
            )

    logging.info("✅ Загрузка баннеров завершена.")
