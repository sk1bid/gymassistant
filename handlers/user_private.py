import asyncio
import logging
import time
from typing import List

from aiogram import F, Router, types
# Импорт необходимых исключений Aiogram
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter, CommandStart, or_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

# Импорт ORM-функций (обновите пути при необходимости)
from database.orm_query import (
    orm_add_user,
    orm_update_user,
    orm_add_program,
    orm_get_user_by_id,
    orm_get_programs,
    orm_turn_on_off_program,
    orm_add_training_day,
    orm_get_exercises,
    orm_add_user_exercise,
    orm_update_user_exercise,
    orm_get_user_exercise,
    orm_delete_exercise,
    move_exercise_up,
    move_exercise_down,
    orm_delete_program,
    orm_get_exercise,
    orm_update_exercise_set,
    orm_delete_exercise_set,
    orm_add_exercise_set,
    orm_get_exercise_set,
    orm_get_exercise_sets,
    orm_add_set,
    orm_get_sets_by_session,
    orm_update_program,
    orm_update_exercise,
    orm_get_categories,
    orm_delete_user_exercise,
    orm_add_training_session,
    orm_get_program, orm_get_sets,
)
# Ваши функции для меню/кнопок
from handlers.menu_processing import get_menu_content
from kbds.inline import MenuCallBack, get_url_btns, error_btns, get_callback_btns
from kbds.reply import get_keyboard
from utils.separator import get_action_part

# Создаём роутер
user_private_router = Router()
user_private_router.message.filter(F.chat.type == "private")


# ================== STATES ==================
class AddUser(StatesGroup):
    user_id = State()
    name = State()
    weight = State()

    user_for_change = None


class AddTrainingProgram(StatesGroup):
    name = State()
    user_id = State()

    trp_for_change = None


class TrainingProcess(StatesGroup):
    """
    Состояния для процесса тренировки.
    """
    rest = State()
    circular_rest = State()
    training_day_id = State()
    exercise_index = State()
    set_index = State()
    reps = State()
    change_reps = State()
    weight = State()
    change_weight = State()
    accept_results = State()
    choose_change = State()

    # Для круговой тренировки
    circular_current_round = State()
    circular_exercise_index = State()
    current_circular_exercise_id = State()


class AddExercise(StatesGroup):
    name = State()
    description = State()
    category_id = State()
    program_id = State()
    training_day_id = State()
    image = State()
    user_id = State()

    exercise_for_change = None


# ================== HELPERS ==================
async def send_error_message(message: types.Message, error: Exception):
    logging.exception(f"Произошла ошибка: {error}")
    btns = {"Написать разработчику": "https://t.me/cg_skbid"}
    await message.answer(
        "Произошла ошибка, попробуйте позже.",
        reply_markup=get_url_btns(btns=btns, sizes=(1,)),
    )


@user_private_router.message(StateFilter(None), CommandStart())
async def send_welcome(message: types.Message, state: FSMContext, session: AsyncSession):
    start_time = time.monotonic()
    user_id = message.from_user.id
    try:
        user = await orm_get_user_by_id(session, user_id)
        if user:
            await message.answer(f"Вы уже зарегистрированы как {user.name}.")
            media, reply_markup = await get_menu_content(session, level=0, action="main")
            await message.answer_photo(photo=media.media, caption=media.caption, reply_markup=reply_markup)
        else:
            await message.answer("Привет, я твой виртуальный тренер. Давай тебя зарегистрируем. Напиши свое имя:")
            await state.set_state(AddUser.name)
            await state.update_data(user_id=int(user_id))
    except Exception as e:
        logging.exception(f"Ошибка в send_welcome: {e}")
        btns = {"Написать разработчику": "https://t.me/cg_skbid"}
        await message.answer("Произошла ошибка, попробуйте позже.",
                             reply_markup=get_url_btns(btns=btns, sizes=(1,)))
    finally:
        duration = time.monotonic() - start_time
        logging.info(f"Обработка send_welcome заняла {duration:.2f} секунд")


@user_private_router.message(StateFilter(AddUser.name.state, AddUser.weight.state), Command("cancel"))
@user_private_router.message(StateFilter(AddUser.name.state, AddUser.weight.state), F.text.casefold() == "отмена")
async def cancel_registration(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Действия отменены\n\nЧтобы продолжить регистрацию, воспользуйтесь командой /start")


@user_private_router.message(AddUser.name, F.text)
async def add_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer(f"Отлично, {message.text}. Введите ваш вес:")
    await state.set_state(AddUser.weight)


@user_private_router.message(AddUser.weight, F.text)
async def add_weight(message: types.Message, state: FSMContext, session: AsyncSession):
    try:
        weight = float(message.text.replace(',', '.'))
        await state.update_data(weight=weight)
    except ValueError:
        await message.answer("Пожалуйста, введите корректное числовое значение для веса.")
        return

    data = await state.get_data()
    try:
        user_for_change = data.get('user_for_change')
        if user_for_change:
            await orm_update_user(session, user_for_change.id, data)
        else:
            await orm_add_user(session, data)

        await message.answer("Прекрасно, вы зарегистрированы в системе!\nДля навигации используйте интерактивное меню.")
        await state.clear()
        media, reply_markup = await get_menu_content(session, level=0, action="main")
        await message.answer_photo(photo=media.media, caption=media.caption, reply_markup=reply_markup)

    except Exception as e:
        logging.exception(f"Ошибка при добавлении пользователя: {e}")
        btns = {"Написать разработчику": "https://t.me/cg_skbid"}
        await message.answer("Произошла ошибка, попробуйте позже.",
                             reply_markup=get_url_btns(btns=btns, sizes=(1,)))
        await state.clear()


#################################### Добавление тренировочной программы ####################################

@user_private_router.callback_query(StateFilter(None), F.data == "adding_program")
async def ask_program_name(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите название программы тренировок:")
    await state.set_state(AddTrainingProgram.name)
    await callback.answer()


@user_private_router.message(StateFilter(AddTrainingProgram.name.state), Command("cancel"))
@user_private_router.message(StateFilter(AddTrainingProgram.name.state), F.text.casefold() == "отмена")
async def cancel_training_program(message: types.Message, state: FSMContext, session: AsyncSession):
    await state.clear()
    await message.answer("Действия отменены")
    media, reply_markup = await get_menu_content(session, level=1, action="program", user_id=message.from_user.id)
    await message.answer_photo(photo=media.media, caption=media.caption, reply_markup=reply_markup)


@user_private_router.message(AddTrainingProgram.name, F.text)
async def add_training_program_name(message: types.Message, state: FSMContext, session: AsyncSession):
    start_time = time.monotonic()
    user_id = message.from_user.id

    if len(message.text) > 15:
        await message.answer("Пожалуйста, введите название короче 15 символов:")
        return

    await state.update_data(user_id=user_id, name=message.text)
    data = await state.get_data()
    try:
        training_program_for_change = data.get('training_program_for_change')
        user_programs = await orm_get_programs(session, user_id)

        if training_program_for_change:
            await orm_update_program(session, training_program_for_change.id, data)
        else:
            await orm_add_program(session, data)
            user_programs = await orm_get_programs(session, user_id)
            await orm_turn_on_off_program(session, user_id, user_programs[-1].id)
        for day in ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]:
            await orm_add_training_day(session, day_of_week=day, program_id=user_programs[-1].id)

    except Exception as e:
        logging.exception(f"Ошибка при добавлении программы: {e}")
        btns = {"Написать разработчику": "https://t.me/cg_skbid"}
        await message.answer("Произошла ошибка, попробуйте позже.",
                             reply_markup=get_url_btns(btns=btns, sizes=(1,)))
        await state.clear()
        return

    await message.answer("Готово!")
    media, reply_markup = await get_menu_content(session, level=1, action="program", user_id=user_id)
    await message.answer_photo(photo=media.media, caption=media.caption, reply_markup=reply_markup)
    await state.clear()

    duration = time.monotonic() - start_time
    logging.info(f"Обработка add_training_program_name заняла {duration:.2f} секунд")


###########################################################################################

async def clicked_btn(callback_data: MenuCallBack, state: FSMContext, selected_id, clicked_id,
                      callback: types.CallbackQuery,
                      session: AsyncSession):
    new_selected_id = None if selected_id == clicked_id else clicked_id

    # Если action начинается с "to_edit" - переключаем упражнение
    if get_action_part(callback_data.action) == "to_edit":
        await state.update_data(selected_exercise_id=new_selected_id)
    elif get_action_part(callback_data.action) == "to_del_prgm":
        await state.update_data(selected_program_id=new_selected_id)

    media, reply_markup = await get_menu_content(
        session,
        level=callback_data.level,
        action=callback_data.action,
        training_program_id=callback_data.program_id,
        exercise_id=new_selected_id,
        page=callback_data.page,
        training_day_id=callback_data.training_day_id,
        user_id=callback.from_user.id,
        category_id=callback_data.category_id,
        empty=callback_data.empty,
        circle_training=callback_data.circle_training,
    )

    try:
        await callback.message.edit_media(media=media, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            pass  # Игнорируем, если контент действительно не изменился
        else:
            logging.warning(f"Ошибка при edit_media: {e}")

    await callback.answer()


#################################### Добавление собственного упражнения ####################################

# Добавление нового упражнения пользователем
@user_private_router.callback_query(
    StateFilter(None),
    or_f(
        MenuCallBack.filter(F.action == "add_u_excs"),
        MenuCallBack.filter(F.action == "shd/add_u_excs"),
    )
)
async def add_exercise_callback_handler(
        callback: types.CallbackQuery,
        callback_data: MenuCallBack,
        state: FSMContext
):
    training_day_id = callback_data.training_day_id
    program_id = callback_data.program_id
    category_id = callback_data.category_id
    empty = callback_data.empty
    await callback.message.answer("Введите название упражнения:", reply_markup=types.ReplyKeyboardRemove())
    await callback.answer()

    user_id = callback.from_user.id
    # Определяем источник добавления упражнения
    if callback_data.action == "add_u_excs":
        origin = "program_settings"
    elif callback_data.action == "shd/add_u_excs":
        origin = "schedule"
    else:
        origin = "unknown"

    # Обновляем данные состояния, включая origin
    await state.update_data(
        training_day_id=training_day_id,
        program_id=program_id,
        category_id=category_id,
        user_id=user_id,
        origin=origin,
        empty=empty,
        circle_training=callback_data.circle_training,
    )
    await state.set_state(AddExercise.name)


# Изменение уже существующего упражнения
@user_private_router.callback_query(StateFilter(None), or_f(
    MenuCallBack.filter(F.action == "change_u_excs"),
    MenuCallBack.filter(F.action == "shd/change_u_excs")
))
async def change_exercise_callback(callback: types.CallbackQuery, callback_data: MenuCallBack, state: FSMContext,
                                   session: AsyncSession):
    exercise_id = callback_data.exercise_id
    training_day_id = callback_data.training_day_id
    program_id = callback_data.program_id
    category_id = callback_data.category_id
    empty = callback_data.empty

    exercise_for_change = await orm_get_user_exercise(session, exercise_id)
    AddExercise.exercise_for_change = exercise_for_change

    await state.update_data(training_day_id=training_day_id, program_id=program_id, category_id=category_id)
    await callback.answer()
    await callback.message.answer("Введите название упражнения:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(AddExercise.name)


@user_private_router.message(
    StateFilter(AddExercise.name.state, AddExercise.category_id.state, AddExercise.description.state),
    Command("cancel"))
@user_private_router.message(
    StateFilter(AddExercise.name.state, AddExercise.category_id.state, AddExercise.description.state),
    F.text.casefold() == "отмена")
async def cancel_add_exercise(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    origin = data.get('origin')
    if origin == "schedule":
        action = "shd/custom_excs"
        level = 7
    elif origin == "program_settings":
        level = 7
        action = "custom_excs"
    else:
        action = "main"
        level = 0
    media, reply_markup = await get_menu_content(
        session=session,
        level=level,
        action=action,
        page=1,
        training_day_id=data.get("training_day_id"),
        category_id=data.get("category_id"),
        training_program_id=data.get("program_id"),
        user_id=data.get("user_id"),
        empty=data.get("empty"),
        circle_training=data.get("circle_training")
    )
    await state.clear()
    await message.answer_photo(photo=media.media, caption=media.caption, reply_markup=reply_markup)


@user_private_router.message(AddExercise.name, F.text)
async def add_exercise_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите описание упражнения")
    await state.set_state(AddExercise.description)


@user_private_router.message(AddExercise.description)
async def add_exercise_description(
        message: types.Message,
        state: FSMContext,
        session: AsyncSession
):
    await state.update_data(description=message.text)
    data = await state.get_data()
    try:
        if data.get("category_id"):
            if AddExercise.exercise_for_change:
                await orm_update_user_exercise(session, AddExercise.exercise_for_change.id, data)
            else:
                await orm_add_user_exercise(session, data)

            await message.answer("Упражнение добавлено/изменено")

            # Определяем, куда вернуть пользователя на основе origin
            origin = data.get('origin')
            if origin == "schedule":
                action = "shd/custom_excs"
                level = 7
            elif origin == "program_settings":
                level = 7
                action = "custom_excs"
            else:
                action = "main"
                level = 0
            media, reply_markup = await get_menu_content(
                session=session,
                level=level,
                action=action,
                page=1,
                training_day_id=data.get("training_day_id"),
                category_id=data.get("category_id"),
                training_program_id=data.get("program_id"),
                user_id=data.get("user_id"),
                empty=data.get("empty"),
                circle_training=data.get("circle_training")
            )
            await message.answer_photo(photo=media.media, caption=media.caption, reply_markup=reply_markup)
            await state.clear()
        else:
            categories = await orm_get_categories(session, message.from_user.id)
            btns = {category.name: str(category.id) for category, _ in categories}
            await message.answer("Выберите категорию", reply_markup=get_callback_btns(btns=btns))
            await state.set_state(AddExercise.category_id)
    except Exception as e:
        logging.exception(f"Ошибка при добавлении упражнения: {e}")
        btns = {"Написать разработчику": "https://t.me/cg_skbid"}
        await message.answer(
            f"Ошибка: \n{str(e)}\nОбратитесь к администратору.",
            reply_markup=get_url_btns(btns=btns, sizes=(1,))
        )
        await state.clear()


@user_private_router.callback_query(AddExercise.category_id)
async def category_choice(callback: types.CallbackQuery, state: FSMContext,
                          session: AsyncSession):
    categories = await orm_get_categories(session, callback.from_user.id)
    category_ids = [category.id for category, _ in categories]
    if int(callback.data) in category_ids:
        await callback.answer()
        await state.update_data(category_id=int(callback.data))
        data = await state.get_data()
        if AddExercise.exercise_for_change:
            await orm_update_user_exercise(session, AddExercise.exercise_for_change.id, data)
        else:
            await orm_add_user_exercise(session, data)

        await callback.message.answer("Упражнение добавлено/изменено")

        # Получаем origin из состояния
        origin = data.get('origin')
        if origin == "schedule":
            action = "shd/custom_excs"
            level = 7
        elif origin == "program_settings":
            level = 7
            action = "custom_excs"
        else:
            action = "main"
            level = 0
        media, reply_markup = await get_menu_content(
            session=session,
            level=level,
            action=action,
            page=1,
            training_day_id=data.get("training_day_id"),
            category_id=data.get("category_id"),
            training_program_id=data.get("program_id"),
            user_id=data.get("user_id"),
            empty=data.get("empty"),
            circle_training=data.get("circle_training")

        )
        await callback.message.answer_photo(photo=media.media, caption=media.caption, reply_markup=reply_markup)
        await state.clear()
    else:
        await callback.message.answer('Выберите категорию из кнопок.')
        await callback.answer()


@user_private_router.message(AddExercise.category_id)
async def category_choice2(message: types.Message):
    await message.answer("'Выберите категорию из кнопок.'")


########################################################################################################################

@user_private_router.callback_query(MenuCallBack.filter())
async def user_menu(callback: types.CallbackQuery, callback_data: MenuCallBack, session: AsyncSession,
                    state: FSMContext):
    start_time = time.monotonic()
    try:
        action = callback_data.action
        logging.info(f"Получен callback от пользователя {callback.from_user.id}: {callback_data}")

        user_data = await state.get_data()
        selected_exercise_id = user_data.get("selected_exercise_id")
        selected_program_id = user_data.get("selected_program_id")

        if get_action_part(action) == "to_edit":
            await clicked_btn(session=session, callback_data=callback_data, state=state,
                              selected_id=selected_exercise_id, callback=callback,
                              clicked_id=callback_data.exercise_id)

        elif get_action_part(action).startswith("del"):
            if get_action_part(action).__contains__("custom"):
                await orm_delete_user_exercise(session, callback_data.exercise_id)
            else:
                await orm_delete_exercise(session, callback_data.exercise_id)
            await state.update_data(selected_exercise_id=None)

            media, reply_markup = await get_menu_content(
                session,
                level=callback_data.level,
                action="to_edit",
                training_program_id=callback_data.program_id,
                exercise_id=None,
                page=callback_data.page,
                training_day_id=callback_data.training_day_id,
                user_id=callback.from_user.id,
                category_id=callback_data.category_id,
                year=callback_data.year,
                month=callback_data.month,
                set_id=callback_data.set_id,
                empty=callback_data.empty,
                circle_training=callback_data.circle_training,
                session_number=callback_data.session_number,
                exercises_page=callback_data.exercises_page,
            )

            if action.startswith("shd/"):
                media, reply_markup = await get_menu_content(
                    session,
                    level=callback_data.level,
                    action="shd/to_edit",
                    training_program_id=callback_data.program_id,
                    exercise_id=None,
                    page=callback_data.page,
                    training_day_id=callback_data.training_day_id,
                    user_id=callback.from_user.id,
                    category_id=callback_data.category_id,
                    year=callback_data.year,
                    month=callback_data.month,
                    set_id=callback_data.set_id,
                    empty=callback_data.empty,
                    circle_training=callback_data.circle_training,
                    session_number=callback_data.session_number,
                    exercises_page=callback_data.exercises_page,
                )

            try:
                await callback.message.edit_media(media=media, reply_markup=reply_markup)
            except TelegramBadRequest as e:
                if "message is not modified" in str(e):
                    pass
                else:
                    logging.warning(f"Ошибка при edit_media: {e}")

            await callback.answer("Упражнение удалено.")

        elif get_action_part(action).startswith("mv"):
            if get_action_part(action) == "mv_up":
                await callback.answer(await move_exercise_up(session, callback_data.exercise_id))
            elif get_action_part(action) == "mv_down":
                await callback.answer(await move_exercise_down(session, callback_data.exercise_id))

            media, reply_markup = await get_menu_content(
                session,
                level=callback_data.level,
                action="to_edit",
                training_program_id=callback_data.program_id,
                exercise_id=callback_data.exercise_id,
                page=callback_data.page,
                training_day_id=callback_data.training_day_id,
                user_id=callback.from_user.id,
                category_id=callback_data.category_id,
                year=callback_data.year,
                month=callback_data.month,
                set_id=callback_data.set_id,
                empty=callback_data.empty,
                circle_training=callback_data.circle_training,
                session_number=callback_data.session_number,
                exercises_page=callback_data.exercises_page,
            )

            if action.startswith("shd/"):
                media, reply_markup = await get_menu_content(
                    session,
                    level=callback_data.level,
                    action="shd/to_edit",
                    training_program_id=callback_data.program_id,
                    exercise_id=callback_data.exercise_id,
                    page=callback_data.page,
                    training_day_id=callback_data.training_day_id,
                    user_id=callback.from_user.id,
                    category_id=callback_data.category_id,
                    year=callback_data.year,
                    month=callback_data.month,
                    set_id=callback_data.set_id,
                    empty=callback_data.empty,
                    circle_training=callback_data.circle_training,
                    session_number=callback_data.session_number,
                    exercises_page=callback_data.exercises_page,
                )
            try:
                await callback.message.edit_media(media=media, reply_markup=reply_markup)
            except TelegramBadRequest as e:
                if "message is not modified" in str(e):
                    pass
                else:
                    logging.warning(f"Ошибка при edit_media: {e}")

        elif get_action_part(action) == "to_del_prgm":
            await clicked_btn(session=session, callback_data=callback_data, state=state,
                              selected_id=selected_program_id, callback=callback, clicked_id=callback_data.program_id)

        elif get_action_part(action) == "prgm_del":
            await orm_delete_program(session, callback_data.program_id)
            await state.update_data(selected_program_id=None)

            media, reply_markup = await get_menu_content(
                session,
                level=callback_data.level,
                action="program",
                training_program_id=None,
                exercise_id=None,
                page=callback_data.page,
                training_day_id=callback_data.training_day_id,
                user_id=callback.from_user.id,
                category_id=callback_data.category_id,
                year=callback_data.year,
                month=callback_data.month,
                set_id=callback_data.set_id,
                empty=callback_data.empty,
                circle_training=callback_data.circle_training,
                session_number=callback_data.session_number,
                exercises_page=callback_data.exercises_page,
            )
            try:
                await callback.message.edit_media(media=media, reply_markup=reply_markup)
            except TelegramBadRequest as e:
                if "message is not modified" in str(e):
                    pass
                else:
                    logging.warning(f"Ошибка при edit_media: {e}")

            await callback.answer("Программа удалена.")

        elif get_action_part(action).startswith("➕") or get_action_part(action).startswith("➖"):
            parts = get_action_part(action).split("_")
            operation = parts[0]  # "➕" или "➖"
            increment = int(parts[1])
            field = parts[2]
            set_id = callback_data.set_id

            user_exercise = await orm_get_exercise(session, callback_data.exercise_id)
            user_exercise_set = await orm_get_exercise_set(session, set_id)

            if field == "reps":
                new_reps = (
                    user_exercise_set.reps + increment
                    if operation == "➕"
                    else max(1, user_exercise_set.reps - increment)
                )
                await orm_update_exercise_set(session, set_id, new_reps)

            elif field == "sets":
                new_sets = (
                    user_exercise.base_sets + increment
                    if operation == "➕"
                    else max(1, user_exercise.base_sets - increment)
                )
                await orm_update_exercise(session, callback_data.exercise_id, {"sets": new_sets})

                if operation == "➕":
                    await orm_add_exercise_set(session, callback_data.exercise_id, user_exercise.base_reps)
                elif operation == "➖":
                    exercise_sets = await orm_get_exercise_sets(session, callback_data.exercise_id)
                    if len(exercise_sets) > 1:
                        last_set_id = exercise_sets[-1].id
                        await orm_delete_exercise_set(session, last_set_id)

            media, reply_markup = await get_menu_content(
                session,
                level=callback_data.level,
                action=f"{operation}_{field}",
                training_program_id=callback_data.program_id,
                exercise_id=callback_data.exercise_id,
                page=callback_data.page,
                training_day_id=callback_data.training_day_id,
                user_id=callback.from_user.id,
                category_id=callback_data.category_id,
                year=callback_data.year,
                month=callback_data.month,
                set_id=callback_data.set_id,
                empty=callback_data.empty,
                circle_training=callback_data.circle_training,
                session_number=callback_data.session_number,
                exercises_page=callback_data.exercises_page,
            )
            if action.startswith("shd/"):
                media, reply_markup = await get_menu_content(
                    session,
                    level=callback_data.level,
                    action=f"shd/{operation}_{field}",
                    training_program_id=callback_data.program_id,
                    exercise_id=callback_data.exercise_id,
                    page=callback_data.page,
                    training_day_id=callback_data.training_day_id,
                    user_id=callback.from_user.id,
                    category_id=callback_data.category_id,
                    year=callback_data.year,
                    month=callback_data.month,
                    set_id=callback_data.set_id,
                    circle_training=callback_data.circle_training,
                    session_number=callback_data.session_number,
                    exercises_page=callback_data.exercises_page,
                )
            try:
                await callback.message.edit_media(media=media, reply_markup=reply_markup)
            except TelegramBadRequest as e:
                if "message is not modified" in str(e):
                    pass
                else:
                    logging.warning(f"Ошибка при edit_media: {e}")

            await callback.answer()

        elif get_action_part(action) == "training_process":
            media, reply_markup = await get_menu_content(
                session,
                level=callback_data.level,
                action=action,
                training_program_id=callback_data.program_id,
                exercise_id=callback_data.exercise_id,
                page=callback_data.page,
                training_day_id=callback_data.training_day_id,
                user_id=callback.from_user.id,
                category_id=callback_data.category_id,
                year=callback_data.year,
                month=callback_data.month,
                set_id=callback_data.set_id,
                empty=callback_data.empty,
                session_number=callback_data.session_number,
                exercises_page=callback_data.exercises_page,
            )
            try:
                await callback.message.edit_media(media=media, reply_markup=reply_markup)
            except TelegramBadRequest as e:
                if "message is not modified" in str(e):
                    pass
                else:
                    logging.warning(f"Ошибка при edit_media: {e}")

            await callback.answer()
            await handle_start_training_process(callback, callback_data, state, session)

        elif get_action_part(action) == "finish_training":
            try:
                await callback.answer()
                media, reply_markup = await get_menu_content(
                    session,
                    level=callback_data.level,
                    action=action,
                    training_program_id=callback_data.program_id,
                    exercise_id=callback_data.exercise_id,
                    page=callback_data.page,
                    training_day_id=callback_data.training_day_id,
                    user_id=callback.from_user.id,
                    category_id=callback_data.category_id,
                    year=callback_data.year,
                    month=callback_data.month,
                    set_id=callback_data.set_id,
                    empty=callback_data.empty,
                    circle_training=callback_data.circle_training,
                    session_number=callback_data.session_number,
                    exercises_page=callback_data.exercises_page,
                )
                try:
                    await callback.message.edit_media(media=media, reply_markup=reply_markup)
                except TelegramBadRequest as e:
                    if "message is not modified" in str(e):
                        pass
                    else:
                        logging.warning(f"Ошибка при edit_media: {e}")

                user_data = await state.get_data()
                bot_message_id = user_data.get('bot_message_id')
                if bot_message_id:
                    try:
                        await callback.message.bot.delete_message(chat_id=callback.message.chat.id,
                                                                  message_id=bot_message_id)
                    except TelegramBadRequest as e:
                        if "message to delete not found" in str(e):
                            pass
                        else:
                            logging.warning(f"Не удалось удалить сообщение бота: {e}")
                rest_message_id = user_data.get("rest_message_id")
                if rest_message_id:
                    try:
                        await callback.message.bot.delete_message(chat_id=callback.message.chat.id,
                                                                  message_id=rest_message_id)
                    except TelegramBadRequest as e:
                        if "message to delete not found" not in str(e):
                            logging.warning(f"Не удалось удалить сообщение об отдыхе: {e}")
                await state.clear()
                await state.update_data(rest_ended=True)
            except Exception as e:
                logging.warning(f"Не удалось удалить сообщение бота: {e}")

        else:
            # Все остальные действия — просто обновляем меню
            media, reply_markup = await get_menu_content(
                session,
                level=callback_data.level,
                action=action,
                training_program_id=callback_data.program_id,
                exercise_id=callback_data.exercise_id,
                page=callback_data.page,
                training_day_id=callback_data.training_day_id,
                user_id=callback.from_user.id,
                category_id=callback_data.category_id,
                year=callback_data.year,
                month=callback_data.month,
                set_id=callback_data.set_id,
                empty=callback_data.empty,
                circle_training=callback_data.circle_training,
                session_number=callback_data.session_number,
                exercises_page=callback_data.exercises_page,
            )
            await state.update_data(selected_exercise_id=None, selected_program_id=None)
            try:
                await callback.message.edit_media(media=media, reply_markup=reply_markup)
            except TelegramBadRequest as e:
                if "message is not modified" in str(e):
                    pass
                else:
                    logging.warning(f"Ошибка при edit_media: {e}")
            await callback.answer()

    except Exception as e:
        if "message is not modified" in str(e):
            pass  # Игнорируем
        else:
            await callback.message.answer(f"Произошла ошибка, попробуйте позже. {e}",
                                          reply_markup=error_btns())
    finally:
        duration = time.monotonic() - start_time
        logging.info(f"Обработка user_menu заняла {duration:.2f} секунд")


# ------------------ Starting Training Process ------------------
@user_private_router.callback_query(MenuCallBack.filter())
async def handle_start_training_process(
        callback: types.CallbackQuery,
        callback_data: MenuCallBack,
        state: FSMContext,
        session: AsyncSession,
):
    """
    Handles the start of the training process by:
    1. Creating a training session in the DB.
    2. Saving the session ID in FSMContext.
    3. Initiating the training flow.
    """
    user_id = callback.from_user.id

    try:
        # Create a new training session
        new_session = await orm_add_training_session(
            session,
            {
                "user_id": user_id,
                "note": "Запуск тренировки",
            },
        )

        user = await orm_get_user_by_id(session, user_id)
        if not user:
            await callback.message.answer("Пользователь не найден.")
            await state.clear()
            return

        training_program = await orm_get_program(session, user.actual_program_id)
        if not training_program:
            await callback.message.answer("Тренировочная программа не найдена.")
            await state.clear()
            return

        circular_rounds = training_program.circular_rounds
        rest_between_exercise = training_program.rest_between_exercise
        circular_rest_between_rounds = training_program.circular_rest_between_rounds
        circular_rest_between_exercise = training_program.circular_rest_between_exercise
        rest_between_set = training_program.rest_between_set

        # Save training session ID and related data in FSMContext
        training_session_id = str(new_session.id)
        await state.set_state(TrainingProcess.exercise_index)
        await state.update_data(
            training_session_id=training_session_id,
            exercise_index=0,
            set_index=1,
            training_day_id=callback_data.training_day_id,
            circular_rounds=circular_rounds,
            rest_between_exercise=rest_between_exercise,
            rest_between_set=rest_between_set,
            circular_rest_between_rounds=circular_rest_between_rounds,
            circular_rest_between_exercise=circular_rest_between_exercise,
            rest_ended=False,
        )

        # Retrieve exercises for the training day
        exercises = await orm_get_exercises(session, callback_data.training_day_id)
        if not exercises:
            await callback.answer("Нет упражнений в этом тренировочном дне.")
            await state.clear()
            return

        # Group exercises into blocks (standard or circuit)
        blocks = group_exercises_into_blocks(exercises)
        if not blocks:
            await callback.answer("Нет упражнений.")
            await state.clear()
            return

        await state.update_data(blocks=[[ex.id for ex in block] for block in blocks], block_index=0)

        # Inform the user about the preparation
        bot_msg = await callback.message.answer("Подготовка к тренировке...")
        await asyncio.sleep(1)
        await state.update_data(bot_message_id=bot_msg.message_id)

        # Start processing the first block
        await process_current_block(callback.message, state, session)
        await callback.answer()
    except Exception as e:
        await send_error_message(callback.message, e)
        await state.clear()


# ------------------ Grouping Exercises ------------------
def group_exercises_into_blocks(exercises: List) -> List[List]:
    """
    Groups exercises into blocks based on whether they are part of a circuit.
    Consecutive circuit exercises are grouped together; others form standard blocks.
    """
    blocks = []
    i = 0
    while i < len(exercises):
        ex = exercises[i]
        if ex.circle_training:
            c_block = [ex]
            i += 1
            while i < len(exercises) and exercises[i].circle_training:
                c_block.append(exercises[i])
                i += 1
            blocks.append(c_block)
        else:
            s_block = [ex]
            i += 1
            while i < len(exercises) and not exercises[i].circle_training:
                s_block.append(exercises[i])
                i += 1
            blocks.append(s_block)
    return blocks


# ------------------ Processing Current Block ------------------
async def process_current_block(
        message: types.Message, state: FSMContext, session: AsyncSession
):
    """
    Processes the current exercise block. Determines if it's a standard or circuit block.
    """
    data = await state.get_data()
    blocks = data.get("blocks", [])
    block_index = data.get("block_index", 0)

    if block_index >= len(blocks):
        # All blocks completed
        await finish_training(message, state, session)
        return

    ex_ids = blocks[block_index]
    ex_objs = []
    is_circuit = True

    # Verify if all exercises in the block are part of a circuit
    for ex_id in ex_ids:
        ex_obj = await orm_get_exercise(session, ex_id)
        if not ex_obj:
            logging.warning(f"Exercise ID {ex_id} not found.")
            continue
        ex_objs.append(ex_obj)
        if not ex_obj.circle_training:
            is_circuit = False

    if is_circuit:
        await state.update_data(
            standard_ex_ids=None,
            standard_ex_idx=None,
            set_index=None,
            circuit_ex_ids=[ex.id for ex in ex_objs],
            circuit_ex_idx=0,
            circuit_round=1,
        )
        await start_circuit_block(message, state, session, ex_objs)
    else:
        await state.update_data(
            circuit_ex_ids=None,
            circuit_ex_idx=None,
            circuit_round=None,
            standard_ex_ids=[ex.id for ex in ex_objs],
            standard_ex_idx=0,
            set_index=1,
        )
        await start_standard_block(message, state, session, ex_objs)


# ------------------ Starting Standard Block ------------------
async def start_standard_block(
        message: types.Message, state: FSMContext, session: AsyncSession, ex_objs: List
):
    """
    Initiates a standard exercise block.
    """
    data = await state.get_data()
    bot_msg_id = data.get("bot_message_id")

    if not ex_objs:
        await message.answer("Нет упражнений в этом блоке.")
        await move_to_next_block_in_day(message, state, session)
        return

    current_ex = ex_objs[0]
    # Получаем список подходов для упражнения
    set_list = await orm_get_sets(session, current_ex.id)
    last_3_sets = set_list[-3:]
    prev_sets = ""
    if last_3_sets:
        for prev_set in last_3_sets:
            prev_sets += (f"<strong>{prev_set.updated.strftime("%d-%m")}"
                          f" 🦾: {prev_set.weight} кг/блок,"
                          f" 🧮: {prev_set.repetitions} повтр.\n</strong>")

    if prev_sets == "":
        prev_sets = "Результаты не обнаружены"

    text = (
        f"Упражнение: <strong>{current_ex.name}</strong>\n\nРезультаты предыдущей тренировки:\n{prev_sets}\n"
        f"Подход <strong>1 из {current_ex.base_sets}</strong> \nВведите количество повторений:"
    )

    try:
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=bot_msg_id,
            text=text,
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            pass
        else:
            logging.warning(f"Ошибка при edit_message_text: {e}")

    current_sets = {"weight": [], "repetitions": []}
    await state.update_data(current_exercise_id=current_ex.id, current_sets=current_sets)
    await state.set_state(TrainingProcess.reps)


# ------------------ Processing After Standard Set ------------------
async def process_standard_after_set(
        message: types.Message, state: FSMContext, session: AsyncSession
):
    """
    Handles the flow after completing a set in a standard block.
    """
    data = await state.get_data()
    bot_msg_id = data["bot_message_id"]
    ex_id = data["current_exercise_id"]
    set_index = data.get("set_index", 1)
    standard_ex_ids = data.get("standard_ex_ids", [])
    standard_ex_idx = data.get("standard_ex_idx", 0)
    rest_between_set = data.get("rest_between_set")

    ex_obj = await orm_get_exercise(session, ex_id)
    total_sets = ex_obj.base_sets if ex_obj else 3

    if set_index < total_sets:
        set_index += 1
        await state.update_data(set_index=set_index)
        rest_text = (f"Подход <strong>{set_index - 1}</strong> завершён! Отдых <strong>{rest_between_set // 60}"
                     f"</strong> мин...")

        # [CHANGE START] Используем try/except для edit_message_text
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=bot_msg_id,
                text=rest_text,
            )
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                pass
            else:
                logging.warning(f"Ошибка при edit_message_text: {e}")
        # [CHANGE END]

        # Set state to 'rest' to handle rest period
        await state.set_state(TrainingProcess.circular_rest)

        # Start the rest period asynchronously
        await asyncio.create_task(
            handle_rest_period(message, state, session, rest_between_set))

        # Получаем список подходов для упражнения
        set_list = await orm_get_sets(session, ex_obj.id)
        last_3_sets = set_list[-3 - (set_index - 1):-(set_index - 1)]
        current_sets = set_list[-(set_index - 1):]
        prev_sets = ""
        if last_3_sets:

            for i, prev_set in enumerate(last_3_sets):
                prev_sets += (f"{prev_set.updated.strftime("%d-%m")}"
                              f" 🦾: {prev_set.weight} кг/блок,"
                              f" 🧮: {prev_set.repetitions} повтр.\n")
                if len(current_sets) > i:
                    if current_sets[i].weight > prev_set.weight:
                        weight_factor = f"💹+{current_sets[i].weight - prev_set.weight}"
                    elif current_sets[i].weight == prev_set.weight:
                        weight_factor = "👌"
                    else:
                        weight_factor = f"📉{current_sets[i].weight - prev_set.weight}"

                    if current_sets[i].repetitions > prev_set.repetitions:
                        reps_factor = f"💹+{current_sets[i].repetitions - prev_set.repetitions}"
                    elif current_sets[i].repetitions == prev_set.repetitions:
                        reps_factor = "👌"
                    else:
                        reps_factor = f"📉{current_sets[i].repetitions - prev_set.repetitions}"
                    prev_sets += (f"<strong>Подход {i + 1} 👇\n"
                                  f"🦾: {current_sets[i].weight} кг/блок {weight_factor}\n"
                                  f"🧮: {current_sets[i].repetitions} повтр. {reps_factor}\n\n</strong>")

        if prev_sets == "":
            prev_sets = "Результаты не обнаружены"

        text = (
            f"Упражнение: <strong>{ex_obj.name}</strong>\n\nРезультаты прошлой тренировки:\n{prev_sets}\n"
            f"Подход <strong>{set_index} из {ex_obj.base_sets}</strong> \nВведите количество повторений:"
        )

        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=bot_msg_id,
                text=text,
            )
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                pass
            else:
                logging.warning(f"Ошибка при edit_message_text: {e}")
        await state.set_state(TrainingProcess.reps)

    else:
        # Move to the next exercise in the block
        standard_ex_idx += 1
        if standard_ex_idx < len(standard_ex_ids):
            await state.update_data(standard_ex_idx=standard_ex_idx, set_index=1)
            next_ex_id = standard_ex_ids[standard_ex_idx]
            next_ex = await orm_get_exercise(session, next_ex_id)
            if not next_ex:
                await message.answer("Следующее упражнение не найдено.")
                await move_to_next_block_in_day(message, state, session)
                return
            await state.update_data(current_exercise_id=next_ex.id)
            set_list = await orm_get_sets(session, next_ex.id)
            last_3_sets = set_list[-3:]
            prev_sets = ""
            if last_3_sets:
                for prev_set in last_3_sets:
                    prev_sets += (f"<strong>{prev_set.updated.strftime("%d-%m")}"
                                  f" 🦾: {prev_set.weight} кг/блок,"
                                  f" 🧮: {prev_set.repetitions} раз\n</strong>")

            if prev_sets == "":
                prev_sets = "Результаты не обнаружены"

            text = (
                f"Следующее упражнение: <strong>{next_ex.name}</strong>\n\n"
                f"Результаты предыдущей тренировки:\n{prev_sets}\n"
                f"Подход <strong>1 из {next_ex.base_sets}</strong> \nВведите количество повторений:"
            )

            try:
                await message.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=bot_msg_id,
                    text=text,
                )
            except TelegramBadRequest as e:
                if "message is not modified" in str(e):
                    pass
                else:
                    logging.warning(f"Ошибка при edit_message_text: {e}")

            await state.set_state(TrainingProcess.reps)
        else:
            # All exercises in the block completed
            await move_to_next_block_in_day(message, state, session)


# ------------------ Starting Circuit Block ------------------
async def start_circuit_block(
        message: types.Message, state: FSMContext, session: AsyncSession, ex_objs: List
):
    """
    Initiates a circuit exercise block.
    """
    data = await state.get_data()
    bot_msg_id = data.get("bot_message_id")
    circular_rounds = data.get("circular_rounds", 1)

    if not ex_objs:
        await message.answer("Нет упражнений в этом блоке.")
        await move_to_next_block_in_day(message, state, session)
        return

    current_ex = ex_objs[0]
    set_list = await orm_get_sets(session, current_ex.id)
    last_3_sets = set_list[-3:]
    prev_sets = ""
    if last_3_sets:
        for prev_set in last_3_sets:
            prev_sets += (f"<strong>{prev_set.updated.strftime("%d-%m")}"
                          f" 🦾: {prev_set.weight} кг/блок,"
                          f" 🧮: {prev_set.repetitions} повтр.\n</strong>")

    if prev_sets == "":
        prev_sets = "Результаты не обнаружены"

    text = (
        f"Блок круговых упражнений\n\n"
        f"Круг <strong>1 из {circular_rounds}</strong>\n\n"
        f"Упражнение: <strong>{current_ex.name}</strong>\n\n"
        f"Результаты предыдущей тренировки:\n{prev_sets}\n"
        "Введите количество повторений:"
    )

    try:
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=bot_msg_id,
            text=text,
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            pass
        else:
            logging.warning(f"Ошибка при edit_message_text: {e}")

    await state.update_data(current_exercise_id=current_ex.id)
    await state.set_state(TrainingProcess.reps)


# ------------------ Processing After Circuit Set ------------------
async def process_circuit_after_set(
        message: types.Message,
        state: FSMContext,
        session: AsyncSession
):
    """
    Handles the flow after completing a set in a circuit block.
    """
    data = await state.get_data()
    bot_msg_id = data["bot_message_id"]
    c_ex_ids = data["circuit_ex_ids"]
    c_idx = data.get("circuit_ex_idx", 0)
    c_round = data.get("circuit_round", 1)
    circular_rounds = data.get("circular_rounds", 1)
    circular_rest_between_rounds = data.get("circular_rest_between_rounds", 60)
    # [ADDED REST BETWEEN EXERCISES]
    circular_rest_between_exercise = data.get("circular_rest_between_exercise", 0)
    c_idx += 1
    if c_idx < len(c_ex_ids):
        # Закончили сет для упражнения c_idx-1,
        # теперь — отдых между упражнениями (если > 0).
        if circular_rest_between_exercise > 0:
            rest_text = (
                f"Отдых <strong>{circular_rest_between_exercise}</strong> сек. перед следующим упражнением..."
            )
            try:
                await message.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=bot_msg_id,
                    text=rest_text,
                )
            except TelegramBadRequest as e:
                if "message is not modified" in str(e):
                    pass
                else:
                    logging.warning(f"Ошибка при edit_message_text: {e}")

            # [ADDED REST BETWEEN EXERCISES] — запускаем короткий отдых
            await state.set_state(TrainingProcess.circular_rest)
            await asyncio.create_task(
                handle_rest_period(message, state, session, circular_rest_between_exercise)
            )
            # После отдыха — идём к следующему упражнению

        await state.update_data(circuit_ex_idx=c_idx)
        next_ex_id = c_ex_ids[c_idx]
        next_ex = await orm_get_exercise(session, next_ex_id)
        if not next_ex:
            await message.answer("Следующее упражнение не найдено.")
            await move_to_next_block_in_day(message, state, session)
            return
        await state.update_data(current_exercise_id=next_ex_id)
        set_list = await orm_get_sets(session, next_ex.id)
        last_3_sets = set_list[-3:]
        prev_sets = ""
        if last_3_sets:
            for prev_set in last_3_sets:
                prev_sets += (f"<strong>{prev_set.updated.strftime("%d-%m")}"
                              f" 🦾: {prev_set.weight} кг/блок,"
                              f" 🧮: {prev_set.repetitions} повтр.\n</strong>")

        if prev_sets == "":
            prev_sets = "Результаты не обнаружены"
        # Выводим инфо о следующем упражнении
        text = (
            f"Круг <strong>{c_round} из {circular_rounds}</strong>\n"
            f"Следующее упражнение: <strong>{next_ex.name}</strong>\n"
            f"Предыдущие результаты:\n{prev_sets}\n"
            "Введите количество повторений:"
        )
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=bot_msg_id,
                text=text,
            )
        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                pass
            else:
                logging.warning(f"Ошибка при edit_message_text: {e}")
        await state.set_state(TrainingProcess.reps)

    else:
        # Completed all exercises in the current round
        if c_round < circular_rounds:
            # Переход к следующему раунду
            c_round += 1
            await state.update_data(circuit_round=c_round)
            rest_text = (
                f"Круг <strong>{c_round - 1}</strong> завершён! Отдых <strong>{circular_rest_between_rounds // 60}"
                f"</strong> мин..."
            )
            try:
                await message.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=bot_msg_id,
                    text=rest_text,
                )
            except TelegramBadRequest as e:
                if "message is not modified" in str(e):
                    pass
                else:
                    logging.warning(f"Ошибка при edit_message_text: {e}")

            # Отдыхаем между раундами
            await state.set_state(TrainingProcess.circular_rest)
            await asyncio.create_task(
                handle_rest_period(message, state, session, circular_rest_between_rounds)
            )
            c_idx = 0
            next_ex_id = c_ex_ids[c_idx]
            await state.update_data(circuit_ex_idx=c_idx)
            next_ex = await orm_get_exercise(session, next_ex_id)
            if not next_ex:
                await message.answer("Следующее упражнение не найдено.")
                await move_to_next_block_in_day(message, state, session)
                return
            await state.update_data(current_exercise_id=next_ex.id)

            set_list = await orm_get_sets(session, next_ex.id)
            last_3_sets = set_list[-3:]
            prev_sets = ""
            if last_3_sets:
                for prev_set in last_3_sets:
                    prev_sets += (f"<strong>{prev_set.updated.strftime("%d-%m")}"
                                  f" 🦾: {prev_set.weight} кг/блок,"
                                  f" 🧮: {prev_set.repetitions} повтр.\n</strong>")

            if prev_sets == "":
                prev_sets = "Результаты не обнаружены"
            # Выводим инфо о следующем упражнении
            text = (
                f"Круг <strong>{c_round} из {circular_rounds}</strong>\n"
                f"Следующее упражнение: <strong>{next_ex.name}</strong>\n"
                f"Предыдущие результаты:\n{prev_sets}\n"
                "Введите количество повторений:"
            )
            try:
                await message.bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=bot_msg_id,
                    text=text,
                )
            except TelegramBadRequest as e:
                if "message is not modified" in str(e):
                    pass
                else:
                    logging.warning(f"Ошибка при edit_message_text: {e}")
            await state.set_state(TrainingProcess.reps)
        else:
            # All rounds completed
            await move_to_next_block_in_day(message, state, session)


# ------------------ Handle Rest Period ------------------
async def handle_rest_period(
        message: types.Message,
        state: FSMContext,
        session: AsyncSession,
        rest_duration: int
):
    """
    Обрабатывает период отдыха:
    1. Удаляет предыдущее сообщение об отдыхе.
    2. Отправляет новое сообщение с обновленным временем (дробными снами).
    3. После завершения отдыха ИЛИ если пользователь завершил отдых досрочно:
       - удаляет последнее сообщение об отдыхе,
       - и, если нужно, отправляет "Отдых закончен..." (но не дублирует при досрочном окончании).
    """

    data = await state.get_data()
    if "rest_ended" not in data:
        await state.update_data(rest_ended=False)

    time_left = rest_duration
    sleep_step = 1  # по желанию - 1, 5, 10 сек

    while time_left > 0:
        # Проверка досрочного окончания
        data = await state.get_data()
        if data.get("rest_ended", False):
            break

        # Удаляем предыдущее сообщение
        rest_message_id = data.get("rest_message_id")
        if rest_message_id:
            try:
                await message.bot.delete_message(chat_id=message.chat.id, message_id=rest_message_id)
            except TelegramBadRequest as e:
                if "message to delete not found" not in str(e):
                    logging.warning(f"Не удалось удалить сообщение об отдыхе: {e}")

        # Считаем оставшиеся минуты
        minutes = time_left // 60
        if minutes > 1:
            new_rest_text = f"Отдыхайте еще <strong>{minutes}</strong> мин..."
        elif minutes == 1:
            new_rest_text = "Отдыхайте еще <strong>1</strong> минуту..."
        else:
            new_rest_text = "Отдых завершен!"
        # Отправляем новое сообщение
        try:
            rest_msg = await message.answer(new_rest_text, reply_markup=get_keyboard("🏄‍♂️ Закончить отдых"))
            await state.update_data(rest_message_id=rest_msg.message_id)
        except TelegramBadRequest as e:
            logging.warning(f"Ошибка при отправке rest-сообщения: {e}")

        # Дробно спим, максимум 60 секунд за "итерацию"
        chunk = min(60, time_left)
        slept = 0
        while slept < chunk:
            await asyncio.sleep(sleep_step)
            slept += sleep_step
            data = await state.get_data()
            if data.get("rest_ended", False):
                break

        if data.get("rest_ended", False):
            break

        time_left -= chunk

    # Удаляем последнее сообщение
    data = await state.get_data()
    await state.update_data(rest_ended=False)
    rest_message_id = data.get("rest_message_id")
    if rest_message_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=rest_message_id)
        except TelegramBadRequest as e:
            if "message to delete not found" not in str(e):
                logging.warning(f"Не удалось удалить последнее сообщение об отдыхе: {e}")

    if data.get("rest_ended", False):
        return
    end_rest_message = await message.answer("Отдых завершен!\n\nАвтоудаление через 5 секунд",
                                            reply_markup=ReplyKeyboardRemove())
    await asyncio.sleep(5)
    if end_rest_message:
        try:
            await end_rest_message.delete()
        except TelegramBadRequest as e:
            if "message to delete not found" not in str(e):
                logging.warning(f"Не удалось удалить последнее сообщение об отдыхе: {e}")


# ------------------ Handle Rest Messages ------------------
@user_private_router.message(StateFilter(TrainingProcess.rest.state, TrainingProcess.circular_rest.state))
async def handle_rest_messages(message: types.Message, state: FSMContext, session: AsyncSession):
    """
    Handles user messages during the rest period.
    Informs the user that the bot is currently resting.
    """
    if message.text == "🏄‍♂️ Закончить отдых":
        await state.update_data(rest_ended=True)
        data = await state.get_data()
        rest_message_id = data.get("rest_message_id")
        if rest_message_id:
            try:
                await message.bot.delete_message(chat_id=message.chat.id, message_id=rest_message_id)
            except TelegramBadRequest as e:
                if "message to delete not found" not in str(e):
                    logging.warning(f"Не удалось удалить последнее сообщение об отдыхе: {e}")

        end_message = await message.answer(
            "Отдых закончен!\n\nАвтоудаление через 5 секунд",
            reply_markup=ReplyKeyboardRemove()
        )
        await message.delete()
        await asyncio.sleep(5)
        await end_message.delete()
        await state.update_data(rest_ended=False)

    else:
        message_rest = await message.reply(
            "Пожалуйста, дождитесь окончания отдыха.\n\nАвтоудаление сообщения через 5 секунд..."
        )
        await asyncio.sleep(5)
        try:
            await message.delete()
        except:
            pass
        try:
            await message_rest.delete()
        except:
            pass


# ------------------ Moving to Next Block ------------------
async def move_to_next_block_in_day(
        message: types.Message, state: FSMContext, session: AsyncSession
):
    """
    Advances to the next exercise block or finishes training if all blocks are done.
    """
    data = await state.get_data()
    blocks = data.get("blocks", [])
    block_index = data.get("block_index", 0) + 1
    await state.update_data(block_index=block_index)

    if block_index >= len(blocks):
        # All blocks completed
        await finish_training(message, state, session)
    else:
        # Continue with the next block
        await process_current_block(message, state, session)


# ------------------ Finishing Training ------------------
async def finish_training(
        message: types.Message, state: FSMContext, session: AsyncSession
):
    """
    Finalizes the training session by compiling results and clearing the state.
    """
    data = await state.get_data()
    training_day_id = data.get("training_day_id")
    training_session_id = data.get("training_session_id")
    bot_msg_id = data.get("bot_message_id")

    # Delete the preparatory message
    if bot_msg_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=bot_msg_id)
        except TelegramBadRequest as e:
            if "message to delete not found" in str(e):
                pass
            else:
                logging.warning(f"Failed to delete bot message: {e}")

    # Compile the training report
    all_exercises = await orm_get_exercises(session, training_day_id)
    result_message = "Тренировка завершена! Отличная работа!\n\nВаши результаты:\n"
    for ex in all_exercises:
        result_message += f"\n👉<strong>Упражнение</strong>: {ex.name}"
        sets = await orm_get_sets_by_session(session, ex.id, training_session_id)
        if sets:
            for s_i, s in enumerate(sets, start=1):
                result_message += (
                    f"\nПодход <strong>{s_i}</strong>: "
                    f"<strong>{s.repetitions}</strong> повтор., вес: <strong>{s.weight}</strong> кг/блок"
                )
        else:
            result_message += "\n   Нет данных о подходах."
    result_message += "\n\nДля завершения тренировки нажмите на кнопку в главном сообщении 👆"
    bot_msg = await message.answer(result_message)
    await state.clear()
    await state.update_data(bot_message_id=bot_msg.message_id)


# ------------------ Processing Reps Input ------------------
@user_private_router.message(TrainingProcess.reps)
async def process_reps_input(
        message: types.Message, state: FSMContext, session: AsyncSession
):
    """
    Handles user input for repetitions in an exercise.
    """
    try:
        reps = int(message.text)
        if reps <= 0:
            raise ValueError("Reps must be positive.")
    except ValueError:
        error_message = await message.reply("Ошибка: введите положительное целое число повторений")
        await asyncio.sleep(3)
        await message.delete()
        await error_message.delete()
        return

    try:
        await message.delete()
    except:
        pass

    await state.update_data(reps=reps)
    data = await state.get_data()
    bot_msg_id = data.get("bot_message_id")

    # Спрашиваем вес
    try:
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=bot_msg_id,
            text="Введите вес снаряда (в кг или блоках):",
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            pass
        else:
            logging.warning(f"Ошибка при edit_message_text: {e}")

    await state.set_state(TrainingProcess.weight)


# ------------------ Processing Weight Input ------------------
@user_private_router.message(TrainingProcess.weight, F.text)
async def process_weight_input(
        message: types.Message, state: FSMContext, session: AsyncSession
):
    """
    Handles user input for weight in an exercise set.
    Saves the set data to the database.
    """
    try:
        weight = float(message.text.replace(",", "."))
        if weight < 0:
            raise ValueError("Weight cannot be negative.")
    except ValueError:
        error_message = await message.reply("Ошибка: вес >= 0.")
        await asyncio.sleep(3)
        await message.delete()
        await error_message.delete()
        return

    try:
        await message.delete()
    except:
        pass

    data = await state.get_data()
    reps = data.get("reps")
    ex_id = data.get("current_exercise_id")
    bot_msg_id = data.get("bot_message_id")
    await state.update_data(weight=weight)
    user_exercise = await orm_get_exercise(session, ex_id)

    try:
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=bot_msg_id,
            text="Ожидание ввода пользователя...",
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            pass
        else:
            logging.warning(f"Ошибка при edit_message_text: {e}")

    accept_message = await message.answer(f"<strong>{user_exercise.name}</strong>\n\n"
                                          f"Результат:\nПовторения: <strong>{reps}</strong>; "
                                          f"Вес: <strong>{weight}</strong> кг/блок\n\n",
                                          reply_markup=get_keyboard("✏️ Изменить",
                                                                    "✅ Продолжить тренировку"))
    await state.update_data(accept_message_id=accept_message.message_id)
    await state.set_state(TrainingProcess.accept_results)


@user_private_router.message(TrainingProcess.accept_results)
async def accept_results(message: types.Message, state: FSMContext, session: AsyncSession):
    if message.text == "✅ Продолжить тренировку":

        data = await state.get_data()
        reps = data.get("reps")
        ex_id = data.get("current_exercise_id")
        training_session_id = data.get("training_session_id")

        try:
            # Save the set to the database
            set_data = {
                "exercise_id": ex_id,
                "weight": data["weight"],
                "repetitions": reps,
                "training_session_id": training_session_id,
            }
            await orm_add_set(session, set_data)
            await message.bot.delete_message(message.chat.id, data["accept_message_id"])
            await message.delete()
            # Determine the type of block and proceed accordingly
            if data.get("standard_ex_ids"):
                await process_standard_after_set(message, state, session)
            elif data.get("circuit_ex_ids"):
                await process_circuit_after_set(message, state, session)
            else:
                await message.answer("Ошибка: не найдено ни standard_ex_ids, ни circuit_ex_ids.")
                await state.clear()
        except Exception as e:
            await send_error_message(message, e)
            await state.clear()
    elif message.text == "✏️ Изменить":

        choose_message = await message.answer("Выберите что нужно изменить:",
                                              reply_markup=get_keyboard("🔢 Повторения",
                                                                        "🏋 Вес",
                                                                        placeholder="Что нужно изменить?"))
        await message.delete()
        await state.update_data(choose_message_id=choose_message.message_id)
        await state.set_state(TrainingProcess.choose_change)


@user_private_router.message(TrainingProcess.choose_change)
async def choose_change(message: types.Message, state: FSMContext):
    await message.delete()
    data = await state.get_data()
    choose_message_id = data.get("choose_message_id")
    await message.bot.delete_message(chat_id=message.chat.id,
                                     message_id=choose_message_id)

    if message.text == "🔢 Повторения":
        try:

            enter_message = await message.answer("Введите кол-во повторений:", reply_markup=ReplyKeyboardRemove())
            await state.update_data(enter_message_id=enter_message.message_id)

        except TelegramBadRequest as e:
            logging.warning(f"Ошибка при редактировании сообщения: {e}")

        await state.set_state(TrainingProcess.change_reps)
    elif message.text == "🏋 Вес":
        await state.set_state(TrainingProcess.change_weight)
        try:

            enter_message = await message.answer("Введите вес снаряда (в кг или блоках):",
                                                 reply_markup=ReplyKeyboardRemove())
            await state.update_data(enter_message_id=enter_message.message_id)

        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                pass
            else:
                logging.warning(f"Ошибка при edit_message_text: {e}")


@user_private_router.message(TrainingProcess.change_reps)
async def process_change_reps_input(
        message: types.Message, state: FSMContext, session: AsyncSession):
    try:
        reps = int(message.text)
        if reps <= 0:
            raise ValueError("Reps must be positive.")
    except ValueError:
        error_message = await message.reply("Ошибка: введите положительное целое число повторений")
        await asyncio.sleep(3)
        await message.delete()
        await error_message.delete()
        return

    try:
        await message.delete()
    except:
        pass

    await state.update_data(reps=reps)
    data = await state.get_data()
    accept_message_id = data.get("accept_message_id")
    reps = data.get("reps")
    weight = data.get("weight")
    ex_id = data.get("current_exercise_id")
    enter_message_id = data.get("enter_message_id")
    user_exercise = await orm_get_exercise(session, ex_id)

    await message.bot.delete_message(chat_id=message.chat.id, message_id=enter_message_id)
    await message.bot.delete_message(chat_id=message.chat.id, message_id=accept_message_id)
    accept_message = await message.answer(f"<strong>{user_exercise.name}</strong>\n\n"
                                          f"Результат:\nПовторения: <strong>{reps}</strong>; "
                                          f"Вес: <strong>{weight}</strong> кг/блок\n\n",
                                          reply_markup=get_keyboard("✏️ Изменить",
                                                                    "✅ Продолжить тренировку"))
    await state.update_data(accept_message_id=accept_message.message_id)
    await state.set_state(TrainingProcess.accept_results)


@user_private_router.message(TrainingProcess.change_weight)
async def process_change_weight_input(
        message: types.Message, state: FSMContext, session: AsyncSession):
    try:
        weight = float(message.text.replace(",", "."))
        if weight < 0:
            raise ValueError("Weight cannot be negative.")
    except ValueError:
        error_message = await message.reply("Ошибка: вес >= 0.")
        await asyncio.sleep(3)
        await message.delete()
        await error_message.delete()
        return

    try:
        await message.delete()
    except:
        pass

    await state.update_data(weight=weight)
    data = await state.get_data()
    accept_message_id = data.get("accept_message_id")
    reps = data.get("reps")
    weight = data.get("weight")
    ex_id = data.get("current_exercise_id")
    enter_message_id = data.get("enter_message_id")
    user_exercise = await orm_get_exercise(session, ex_id)

    await message.bot.delete_message(chat_id=message.chat.id, message_id=enter_message_id)
    await message.bot.delete_message(chat_id=message.chat.id, message_id=accept_message_id)
    accept_message = await message.answer(f"<strong>{user_exercise.name}</strong>\n\n"
                                          f"Результат:\nПовторения: <strong>{reps}</strong>; "
                                          f"Вес: <strong>{weight}</strong> кг/блок\n\n",
                                          reply_markup=get_keyboard("✏️ Изменить",
                                                                    "✅ Продолжить тренировку"))
    await state.update_data(accept_message_id=accept_message.message_id)
    await state.set_state(TrainingProcess.accept_results)
