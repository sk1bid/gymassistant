from asyncio import gather
import time  # Добавлено для измерения времени
import logging  # Добавлено для логирования
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession
from database.orm_query import (
    orm_get_program,
    orm_get_programs,
    orm_get_training_day,
    orm_get_training_days,
    orm_get_exercises,
    orm_get_exercise,
    orm_get_banner,
    orm_get_user_by_id,
    orm_add_training_day,
    orm_add_exercise,
    orm_get_admin_exercise,
    orm_get_categories,
    orm_get_admin_exercises_in_category,
    orm_get_category,
    orm_add_exercise_set,
    orm_get_exercise_sets, orm_turn_on_off_program
)
from kbds.inline import (
    get_user_main_btns,
    get_user_programs_list,
    get_training_day_btns,
    get_profile_btns,
    get_schedule_btns,
    get_category_exercise_btns,
    get_category_btns,
    get_program_btns,
    get_trd_edit_btns,
    get_program_stgs_btns,
    get_edit_exercise_btns,
    get_exercise_settings_btns, get_training_process_btns,
)
from utils.paginator import Paginator
from aiogram.types import InputMediaPhoto

WEEK_DAYS_RU = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]


def exercises_in_program(user_exercises: list):
    if user_exercises:
        caption_text = "<b>Ваши упражнения:</b>\n\n" + "\n".join(
            [f"🔘 <b>{ex.name}</b>" for ex in user_exercises])
    else:
        caption_text = "<strong>Упражнений пока нет. Добавьте новое упражнение!</strong>"
    return caption_text


async def main_menu(session: AsyncSession):
    try:
        banner = await orm_get_banner(session, "main")
        banner_image = InputMediaPhoto(media=banner.image,
                                       caption=f"<strong>{banner.description}</strong>")
        kbds = get_user_main_btns()
        return banner_image, kbds
    except Exception as e:
        logging.exception(f"Ошибка в main_menu: {e}")
        # Возвращаем сообщение об ошибке или дефолтное значение
        return InputMediaPhoto(media='https://postimg.cc/Ty7d15kq',
                               caption="Ошибка при загрузке меню")


async def profile(session: AsyncSession, level: int, menu_name: str, user_id: int):
    try:
        banner, user = await gather(
            orm_get_banner(session, menu_name),
            orm_get_user_by_id(session, user_id)
        )
        banner_image = InputMediaPhoto(media=banner.image,
                                       caption=f"<strong>{banner.description}:\n {user.name} — вес:"
                                               f" {user.weight}</strong>")

        kbds = get_profile_btns(level=level)
        return banner_image, kbds
    except Exception as e:
        logging.exception(f"Ошибка в profile: {e}")
        return InputMediaPhoto(media='https://postimg.cc/Ty7d15kq',
                               caption="Ошибка при загрузке профиля")


async def schedule(session: AsyncSession, level: int, menu_name: str, training_day_id: int, user_id: int):
    try:
        banner, user_data = await gather(
            orm_get_banner(session, "schedule"),
            orm_get_user_by_id(session, user_id)
        )
        user_program = user_data.actual_program_id
        if user_program:
            today = date.today()
            trd_list = await orm_get_training_days(session, user_data.actual_program_id)
            day_of_week_to_id = {td.day_of_week.strip().lower(): td.id for td in trd_list}
            weekday_index = today.weekday()
            day_of_week_rus = WEEK_DAYS_RU[weekday_index].strip().lower()
            user_training_day_id = day_of_week_to_id.get(day_of_week_rus)
            if training_day_id is None:
                training_day_id = user_training_day_id
            user_trd = await orm_get_training_day(session, training_day_id)
            # Проверяем, найден ли тренировочный день
            if user_trd is None:
                banner_image = InputMediaPhoto(
                    media=banner.image,
                    caption="Тренировочный день не найден."
                )
                kbds = get_schedule_btns(
                    level=level,
                    year=today.year,
                    month=today.month,
                    menu_name=menu_name,
                    training_day_id=training_day_id,
                    first_exercise_id=None,
                    active_program=user_program,
                    day_of_week_to_id=day_of_week_to_id,  # Передаем словарь
                )
                return banner_image, kbds

            # Получаем упражнения для тренировочного дня
            user_exercises = await orm_get_exercises(session, training_day_id)

            if not user_exercises:
                exercises_caption = "Нет упражнений на сегодня."
            else:
                exercises_caption = exercises_in_program(user_exercises)

            banner_image = InputMediaPhoto(
                media=banner.image,
                caption=f"{user_trd.day_of_week}\n\n{exercises_caption}"
            )

            first_exercise_id = user_exercises[0].id if user_exercises else None

            kbds = get_schedule_btns(
                level=level,
                year=today.year,
                month=today.month,
                menu_name=menu_name,
                training_day_id=training_day_id,
                first_exercise_id=first_exercise_id,
                active_program=user_program,
                day_of_week_to_id=day_of_week_to_id  # Передаем словарь
            )

            return banner_image, kbds
        else:
            banner_image = InputMediaPhoto(
                media=banner.image,
                caption=f"{banner.description}\n\nНе обнаружена программа тренировок\nСоздайте её прямо сейчас!"
            )
            kbds = get_schedule_btns(
                level=level,
                year=None,
                month=None,
                menu_name=menu_name,
                training_day_id=None,
                first_exercise_id=None,
                active_program=None,
            )
            return banner_image, kbds

    except Exception as e:
        logging.exception(f"Ошибка в schedule: {e}")
        error_image = InputMediaPhoto(
            media='https://postimg.cc/Ty7d15kq',
            caption="Ошибка при загрузке расписания"
        )
        return error_image, None


async def training_process(session: AsyncSession, level: int, training_day_id: int):
    try:
        banner = await orm_get_banner(session, "training_process")
        user_exercises = await orm_get_exercises(session, training_day_id)
        exercises_list = exercises_in_program(user_exercises)
        banner_image = InputMediaPhoto(media=banner.image, caption=banner.description + "\n\n" + exercises_list)
        kbds = get_training_process_btns(level=level, training_day_id=training_day_id)
        return banner_image, kbds
    except Exception as e:
        logging.exception(f"Ошибка в training_process: {e}")
        return InputMediaPhoto(media='https://postimg.cc/Ty7d15kq',
                               caption="Ошибка при загрузке тренировки"), None


async def programs_catalog(session: AsyncSession, level: int, menu_name: str, user_id: int):
    try:
        banner, programs = await gather(
            orm_get_banner(session, menu_name),
            orm_get_programs(session, user_id=user_id)
        )
        user_data = await orm_get_user_by_id(session, user_id)
        banner_image = InputMediaPhoto(media=banner.image, caption=banner.description)

        kbbs = get_user_programs_list(level=level, programs=programs, active_program_id=user_data.actual_program_id)
        return banner_image, kbbs
    except Exception as e:
        logging.exception(f"Ошибка в programs_catalog: {e}")
        return InputMediaPhoto(media='https://postimg.cc/Ty7d15kq',
                               caption="Ошибка при загрузке программ")


def pages(paginator: Paginator, program_name: str):
    btns = {}
    if paginator.has_previous():
        btns["◀ Пред."] = f"previous_{program_name}"
    if paginator.has_next():
        btns["След. ▶"] = f"next_{program_name}"
    return btns


async def program(session: AsyncSession, level: int, training_program_id: int, user_id: int):
    try:
        user_program = await orm_get_program(session, training_program_id)
        banner = await orm_get_banner(session, "user_program")
        user_data = await orm_get_user_by_id(session, user_id)
        if user_data.actual_program_id == user_program.id:
            indicator = "🟢"
        else:
            indicator = "🔴"
        banner_image = InputMediaPhoto(media=banner.image,
                                       caption=f"<strong>{banner.description + user_program.name + ' ' + indicator}"
                                               f"</strong>")
        kbds = get_program_btns(level=level, user_program_id=training_program_id)
        return banner_image, kbds
    except Exception as e:
        logging.exception(f"Ошибка в program: {e}")
        return InputMediaPhoto(media='https://postimg.cc/Ty7d15kq',
                               caption="Ошибка при загрузке программы")


async def program_settings(session: AsyncSession, level: int, training_program_id: int, menu_name: str, user_id: int):
    try:
        user_program = await orm_get_program(session, training_program_id)
        user_data = await orm_get_user_by_id(session, user_id)
        active_program = True if user_data.actual_program_id else False
        banner = await orm_get_banner(session, "user_program")
        if menu_name.split("_")[1] == "on":
            await orm_turn_on_off_program(session, user_id=user_id, program_id=training_program_id)
            active_program = True
        elif menu_name.split("_")[1] == "off":
            await orm_turn_on_off_program(session, user_id=user_id, program_id=None)
            active_program = False
        if active_program:
            indicator = "🟢"
        else:
            indicator = "🔴"
        banner_image = InputMediaPhoto(media=banner.image,
                                       caption=f"<strong>{banner.description + user_program.name + ' ' + indicator}"
                                               f"</strong>")
        kbds = get_program_stgs_btns(level=level, user_program_id=training_program_id, menu_name=menu_name,
                                     active_program=active_program)
        return banner_image, kbds
    except Exception as e:
        logging.exception(f"Ошибка в program_settings: {e}")
        return InputMediaPhoto(media='https://postimg.cc/Ty7d15kq',
                               caption="Ошибка при загрузке настроек программы")


###################################### Тренировочный день #########################
async def training_days(session, level: int, training_program_id: int, page: int):
    try:
        user_program, training_days_list = await gather(
            orm_get_program(session, training_program_id),
            orm_get_training_days(session, training_program_id)
        )
        user_program = user_program
        banner = await orm_get_banner(session, "user_program")

        paginator = Paginator(training_days_list, page=page)
        training_day = paginator.get_page()[0]

        user_exercises = await orm_get_exercises(session, training_day.id)

        caption_text = exercises_in_program(user_exercises)
        image = InputMediaPhoto(
            media=banner.image,
            caption=(
                f"<strong>{banner.description + user_program.name}\n\n"
                f" День {paginator.page} из {paginator.pages} ({training_day.day_of_week})\n\n"
                f"{caption_text}</strong>"
            ),
            parse_mode='HTML'
        )

        pagination_btns = pages(paginator, user_program.name)

        kbds = get_training_day_btns(
            level=level,
            user_program_id=training_program_id,
            program=user_program,
            page=page,
            training_day_id=training_day.id,
            pagination_btns=pagination_btns
        )

        return image, kbds
    except Exception as e:
        logging.exception(f"Ошибка в training_days: {e}")
        return InputMediaPhoto(media='https://postimg.cc/Ty7d15kq',
                               caption="Ошибка при загрузке тренировочных дней")


async def edit_training_day(session: AsyncSession, level: int, training_program_id: int, page: int,
                            training_day_id: int, menu_name: str):
    try:
        user_exercises = await orm_get_exercises(session, training_day_id)
        banner = await orm_get_banner(session, "user_program")
        training_day = await orm_get_training_day(session, training_day_id)
        caption_text = exercises_in_program(user_exercises)
        empty_list = not user_exercises

        user_image = InputMediaPhoto(
            media=banner.image,
            caption=f"<strong>{training_day.day_of_week}\n\n{caption_text}</strong>",
        )

        kbds = get_trd_edit_btns(level=level, program_id=training_program_id, page=page,
                                 training_day_id=training_day_id,
                                 empty_list=empty_list, menu_name=menu_name)

        return user_image, kbds
    except Exception as e:
        logging.exception(f"Ошибка в edit_training_day: {e}")
        return InputMediaPhoto(media='https://postimg.cc/Ty7d15kq',
                               caption="Ошибка при редактировании тренировочного дня")


##################################### Добавление упражнения ###############################
async def show_categories(session: AsyncSession, level: int, training_program_id: int, training_day_id: int, page: int,
                          menu_name: str):
    try:
        user_exercises = await orm_get_exercises(session, training_day_id)
        categories = await orm_get_categories(session)
        user_program = await orm_get_program(session, training_program_id)
        banner = await orm_get_banner(session, "user_program")
        caption_text = exercises_in_program(user_exercises)

        user_image = InputMediaPhoto(
            media=banner.image,
            caption=f"<strong>{banner.description + user_program.name}\n\n{caption_text}\n\n"
                    f"Выберите категорию упражнений</strong>",
        )

        kbds = get_category_btns(
            level=level,
            program_id=training_program_id,
            training_day_id=training_day_id,
            page=page,
            categories=categories,
            menu_name=menu_name,
        )

        return user_image, kbds
    except Exception as e:
        logging.exception(f"Ошибка в show_categories: {e}")
        return InputMediaPhoto(media='https://postimg.cc/Ty7d15kq',
                               caption="Ошибка при загрузке категорий")


async def show_exercises_in_category(session: AsyncSession, level: int, exercise_id: int, training_day_id: int,
                                     page: int, menu_name: str, training_program_id: int, category_id):
    try:
        user_exercises = await orm_get_exercises(session, training_day_id)
        category = await orm_get_category(session, category_id)
        user_program = await orm_get_program(session, training_program_id)
        admin_exercises = await orm_get_admin_exercises_in_category(session, category_id)
        banner = await orm_get_banner(session, "user_program")

        if menu_name.startswith("add"):
            exercise = await orm_get_admin_exercise(session, exercise_id)
            if exercise:
                await orm_add_exercise(session, {
                    "name": exercise.name,
                    "description": exercise.description,
                    "image": exercise.image,
                }, training_day_id)
                user_exercises = await orm_get_exercises(session, training_day_id)
                for _ in range(user_exercises[-1].base_sets):
                    await orm_add_exercise_set(session, user_exercises[-1].id, user_exercises[-1].base_reps)

        caption_text = exercises_in_program(user_exercises)

        user_image = InputMediaPhoto(
            media=banner.image,
            caption=f"<strong>{banner.description + user_program.name}\n\n{caption_text}\n\n"
                    f"Упражнения в категории: {category.name}</strong>",
        )
        kbds = get_category_exercise_btns(level=level,
                                          program_id=training_program_id,
                                          training_day_id=training_day_id,
                                          page=page,
                                          template_exercises=admin_exercises,
                                          menu_name=menu_name)
        return user_image, kbds
    except Exception as e:
        logging.exception(f"Ошибка в show_exercises_in_category: {e}")
        return InputMediaPhoto(media='https://postimg.cc/Ty7d15kq',
                               caption="Ошибка при загрузке упражнений категории")


################################## Изменение упражнения ####################################
async def edit_exercises(session: AsyncSession, level: int, exercise_id: int, training_day_id: int,
                         page: int, menu_name: str, training_program_id: int):
    try:
        user_exercises = await orm_get_exercises(session, training_day_id)
        banner = await orm_get_banner(session, "user_program")
        user_image = InputMediaPhoto(
            media=banner.image,
            caption="<strong>Чтобы изменить упражнение, выберите его из списка:</strong>",
        )

        kbds = get_edit_exercise_btns(level=level, program_id=training_program_id, user_exercises=user_exercises,
                                      page=page, exercise_id=exercise_id,
                                      menu_name=menu_name,
                                      training_day_id=training_day_id)

        return user_image, kbds
    except Exception as e:
        logging.exception(f"Ошибка в edit_exercises: {e}")
        return InputMediaPhoto(media='https://postimg.cc/Ty7d15kq',
                               caption="Ошибка при редактировании упражнения")


async def exercise_settings(session: AsyncSession, level: int, exercise_id: int, training_day_id: int,
                            page: int, menu_name: str, training_program_id: int):
    try:
        user_exercise = await orm_get_exercise(session, exercise_id)
        banner = await orm_get_banner(session, "user_program")
        base_ex_sets = await orm_get_exercise_sets(session, exercise_id)
        user_image = InputMediaPhoto(
            media=banner.image,
            caption="<strong>Добавьте нужное вам количество подходов и повторений</strong>",
        )

        kbds = get_exercise_settings_btns(level=level, menu_name=menu_name, program_id=training_program_id,
                                          page=page, exercise_id=exercise_id,
                                          training_day_id=training_day_id, user_exercise=user_exercise,
                                          base_ex_sets=base_ex_sets)

        return user_image, kbds
    except Exception as e:
        logging.exception(f"Ошибка в exercise_settings: {e}")
        return InputMediaPhoto(media='https://postimg.cc/Ty7d15kq',
                               caption="Ошибка при настройке упражнения")


###################################### Главный обработчик #################################

async def get_menu_content(session: AsyncSession, level: int, menu_name: str, training_program_id: int = None,
                           exercise_id: int = None, page: int = None, training_day_id: int = None, user_id: int = None,
                           category_id: int = None, month: int = None, year: int = None):
    start_time = time.monotonic()
    try:
        if level == 0:
            return await main_menu(session)
        elif level == 1:
            if menu_name == "program":
                return await programs_catalog(session, level, menu_name, user_id)
            elif menu_name == "profile":
                return await profile(session, level, menu_name, user_id)
            elif menu_name in ["schedule", "month_schedule", "t_day"]:
                return await schedule(session, level, menu_name, training_day_id, user_id)
        elif level == 2:
            if menu_name in ["training_process"]:
                return await training_process(session, level, training_day_id)
            return await program(session, level, training_program_id, user_id)
        elif level == 3:
            if menu_name in ["prg_stg", "turn_on_prgm", "turn_off_prgm"] or menu_name.startswith(
                    "to_del_prgm") or menu_name.startswith("del_prgm"):
                return await program_settings(session, level, training_program_id, menu_name, user_id)
            return await training_days(session, level, training_program_id, page)
        elif level == 4:
            return await edit_training_day(session, level, training_program_id, page, training_day_id, menu_name)
        elif level == 5:
            if menu_name.startswith("edit_excs") or menu_name in ["del", "mv"] or menu_name.startswith("to_edit"):
                return await edit_exercises(session, level, exercise_id, training_day_id, page, menu_name,
                                            training_program_id)
            else:
                return await show_categories(session, level, training_program_id, training_day_id, page, menu_name)
        elif level == 6:
            if menu_name in ["ex_setgs"] or menu_name.startswith("➕") or menu_name.startswith("➖"):
                return await exercise_settings(session, level, exercise_id, training_day_id, page, menu_name,
                                               training_program_id)
            return await show_exercises_in_category(session, level, exercise_id, training_day_id, page, menu_name,
                                                    training_program_id, category_id)
        elif level == 7:
            pass
        else:
            logging.warning(f"Неизвестный уровень меню: {level}")
            return InputMediaPhoto(media='https://postimg.cc/Ty7d15kq',
                                   caption="Ошибка: неизвестный уровень меню")
    except Exception as e:
        logging.exception(f"Ошибка в get_menu_content: {e}")
        return InputMediaPhoto(media='https://postimg.cc/Ty7d15kq',
                               caption="Ошибка при загрузке меню")
    finally:
        end_time = time.monotonic()
        duration = end_time - start_time
        logging.info(f"get_menu_content для menu_name='{menu_name}', level={level} заняла {duration:.2f} секунд")
