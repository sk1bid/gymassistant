import uuid
import time
import logging

from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter, CommandStart, or_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from sqlalchemy.ext.asyncio import AsyncSession

# Импорт ORM-функций из вашего модуля
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
    orm_get_sets_by_session, orm_update_program, orm_update_exercise,
)

from handlers.menu_processing import get_menu_content
from kbds.inline import MenuCallBack, get_url_btns, error_btns
from utils.separator import get_action_part

user_private_router = Router()
user_private_router.message.filter(F.chat.type == "private")


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
    training_day_id = State()
    exercise_index = State()
    set_index = State()
    reps = State()
    weight = State()

    training_for_change = None


class AddExercise(StatesGroup):
    name = State()
    description = State()
    category_id = State()
    program_id = State()
    training_day_id = State()
    image = State()
    user_id = State()

    exercise_for_change = None


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

async def clicked_btn(callback_data: MenuCallBack, state: FSMContext, selected_id, callback: types.CallbackQuery,
                      session: AsyncSession, clicked_id):
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
        category_id=callback_data.category_id
    )

    await callback.message.edit_media(media=media, reply_markup=reply_markup)
    await callback.answer()


#################################### Добавление собственного упражнения ####################################

# Добавление нового упражнения пользователем
@user_private_router.callback_query(
    StateFilter(None),
    or_f(
        MenuCallBack.filter(F.action == "add_u_excs"),
        MenuCallBack.filter(F.action == "shd/add_u_excs"),
        MenuCallBack.filter(F.action == "ctg_add_u_excs"),
        MenuCallBack.filter(F.action == "shd/ctg_add_u_excs"),
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

    await callback.message.answer("Введите название упражнения:", reply_markup=types.ReplyKeyboardRemove())
    await callback.answer()

    user_id = callback.from_user.id
    # Определяем источник добавления упражнения
    if callback_data.action == "add_u_excs":
        origin = "program_settings"
    elif callback_data.action == "shd/add_u_excs":
        origin = "schedule"
    elif callback_data.action == "ctg_add_u_excs":
        origin = "ctg_program_settings"
    elif callback_data.action == "shd/ctg_add_u_excs":
        origin = "ctg_schedule"
    else:
        origin = "unknown"

    # Обновляем данные состояния, включая origin
    await state.update_data(
        training_day_id=training_day_id,
        program_id=program_id,
        category_id=category_id,
        user_id=user_id,
        origin=origin  # Сохраняем источник
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
    elif origin == "ctg_program_settings":
        level = 7
        action = "ctg_custom_excs"
    elif origin == "ctg_schedule":
        level = 7
        action = "shd/ctg_custom_excs"
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
        user_id=data.get("user_id")

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
        if AddExercise.exercise_for_change:
            await orm_update_user_exercise(session, AddExercise.exercise_for_change.id, data)
        else:
            await orm_add_user_exercise(session, data)

        await message.answer("Упражнение добавлено/изменено")

        # Получаем origin из состояния
        origin = data.get('origin')

        # Определяем, куда вернуть пользователя на основе origin
        if origin == "schedule":
            action = "shd/custom_excs"
            level = 7
        elif origin == "program_settings":
            level = 7
            action = "custom_excs"
        elif origin == "ctg_add_u_excs":
            level = 7
            action = "ctg_custom_excs"
        elif origin == "shd/ctg_add_u_excs":
            level = 7
            action = "shd/ctg_custom_excs"
        else:
            action = "main"
            level = 0

        await state.clear()

        # Получаем новое меню на основе action и level
        media, reply_markup = await get_menu_content(
            session=session,
            level=level,
            action=action,
            page=1,
            training_day_id=data.get("training_day_id"),
            category_id=data.get("category_id"),
            training_program_id=data.get("program_id"),
            user_id=data.get("user_id")

        )
        await message.answer_photo(photo=media.media, caption=media.caption, reply_markup=reply_markup)
    except Exception as e:
        logging.exception(f"Ошибка при добавлении упражнения: {e}")
        btns = {"Написать разработчику": "https://t.me/cg_skbid"}
        await message.answer(
            f"Ошибка: \n{str(e)}\nОбратитесь к администратору.",
            reply_markup=get_url_btns(btns=btns, sizes=(1,))
        )
        await state.clear()
    finally:
        AddExercise.exercise_for_change = None


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
                )

            await callback.message.edit_media(media=media, reply_markup=reply_markup)
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
                )
            await callback.message.edit_media(media=media, reply_markup=reply_markup)

        elif get_action_part(action) == "to_del_prgm":
            await clicked_btn(session=session, callback_data=callback_data, state=state,
                              selected_id=selected_program_id, callback=callback, clicked_id=callback_data.program_id)

        elif get_action_part(action) == "prgm_del":
            await orm_delete_program(session, callback_data.program_id)
            await orm_turn_on_off_program(session, callback.from_user.id, None)
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
            )
            await callback.message.edit_media(media=media, reply_markup=reply_markup)
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
                new_reps = user_exercise_set.reps + increment if operation == "➕" else max(1,
                                                                                           user_exercise_set.reps - increment)
                await orm_update_exercise_set(session, set_id, new_reps)

            elif field == "sets":
                new_sets = user_exercise.base_sets + increment if operation == "➕" else max(1,
                                                                                            user_exercise.base_sets - increment)
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
                )
            await callback.message.edit_media(media=media, reply_markup=reply_markup)
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
            )
            await callback.message.edit_media(media=media, reply_markup=reply_markup)
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
                )
                await callback.message.edit_media(media=media, reply_markup=reply_markup)
                user_data = await state.get_data()
                bot_message_id = user_data.get('bot_message_id')
                if bot_message_id:
                    await callback.message.bot.delete_message(chat_id=callback.message.chat.id,
                                                              message_id=bot_message_id)
                await state.clear()
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
            )
            await state.update_data(selected_exercise_id=None, selected_program_id=None)
            await callback.message.edit_media(media=media, reply_markup=reply_markup)
            await callback.answer()

    except Exception as e:
        if "message is not modified" in str(e):
            # Игнорируем ошибку, если сообщение не изменилось
            pass
        else:
            await callback.message.answer(f"Произошла ошибка, попробуйте позже. {e}",
                                          reply_markup=error_btns())
    finally:
        duration = time.monotonic() - start_time
        logging.info(f"Обработка user_menu заняла {duration:.2f} секунд")


async def handle_start_training_process(callback: types.CallbackQuery, callback_data: MenuCallBack, state: FSMContext,
                                        session: AsyncSession):
    training_session_id = uuid.uuid4()
    await state.set_state(TrainingProcess.exercise_index)
    await state.update_data(
        training_day_id=callback_data.training_day_id,
        exercise_index=0,
        set_index=1,
        training_session_id=str(training_session_id),
    )

    exercises = await orm_get_exercises(session, callback_data.training_day_id)
    if not exercises:
        await callback.message.answer("Нет упражнений в этом тренировочном дне.")
        await state.clear()
        return

    exercise_ids = [exercise.id for exercise in exercises]
    await state.update_data(exercise_ids=exercise_ids)
    current_exercise = exercises[0]
    await state.update_data(current_exercise_id=current_exercise.id)

    bot_msg = await callback.message.answer(
        f"Начинаем тренировку!\n\nУпражнение: {current_exercise.name}\n{current_exercise.description}\n\n"
        f"Подход 1 из {current_exercise.base_sets}\nВведите количество повторений:"
    )
    await state.update_data(bot_message_id=bot_msg.message_id)
    await state.set_state(TrainingProcess.reps)
    await callback.answer()


@user_private_router.callback_query(MenuCallBack.filter(F.action == "training_process"))
async def start_training_process(callback: types.CallbackQuery, callback_data: MenuCallBack, state: FSMContext,
                                 session: AsyncSession):
    await handle_start_training_process(callback, callback_data, state, session)


@user_private_router.message(TrainingProcess.reps)
async def process_reps_input(message: types.Message, state: FSMContext):
    try:
        reps = int(message.text)
        if reps <= 0:
            raise ValueError
    except ValueError:
        await message.reply("Пожалуйста, введите положительное целое число для повторений.")
        return

    await state.update_data(reps=reps)
    try:
        await message.delete()
    except Exception as e:
        logging.warning(f"Не удалось удалить сообщение пользователя: {e}")

    data = await state.get_data()
    bot_message_id = data.get('bot_message_id')

    await message.bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=bot_message_id,
        text="Введите вес снаряда (в кг):"
    )
    await state.set_state(TrainingProcess.weight)


@user_private_router.message(TrainingProcess.weight)
async def process_weight_input(message: types.Message, state: FSMContext, session: AsyncSession):
    try:
        weight = float(message.text.replace(',', '.'))
        if weight < 0:
            raise ValueError
    except ValueError:
        await message.reply("Пожалуйста, введите неотрицательное число для веса.")
        return

    try:
        await message.delete()
    except Exception as e:
        logging.warning(f"Не удалось удалить сообщение пользователя: {e}")

    data = await state.get_data()
    reps = data['reps']
    current_exercise_id = data['current_exercise_id']
    set_index = data['set_index']
    bot_message_id = data.get('bot_message_id')
    training_session_id = data['training_session_id']

    set_data = {
        'exercise_id': current_exercise_id,
        'weight': weight,
        'repetitions': reps,
        'training_session_id': training_session_id,
    }

    await orm_add_set(session, set_data)
    exercise = await orm_get_exercise(session, current_exercise_id)
    total_sets = exercise.base_sets

    if set_index < total_sets:
        set_index += 1
        await state.update_data(set_index=set_index)

        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=bot_message_id,
            text=f"Подход {set_index} из {total_sets}\nВведите количество повторений:"
        )
        await state.set_state(TrainingProcess.reps)
    else:
        await move_to_next_exercise(message, state, session)


async def move_to_next_exercise(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    exercise_index = data['exercise_index'] + 1
    exercise_ids = data['exercise_ids']
    bot_message_id = data.get('bot_message_id')
    training_day_id = data['training_day_id']
    training_session_id = data['training_session_id']

    if exercise_index < len(exercise_ids):
        await state.update_data(exercise_index=exercise_index, current_exercise_id=exercise_ids[exercise_index],
                                set_index=1)
        current_exercise = await orm_get_exercise(session, exercise_ids[exercise_index])

        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=bot_message_id,
            text=(
                f"Следующее упражнение: {current_exercise.name}\n"
                f"{current_exercise.description}\n\n"
                f"Подход 1 из {current_exercise.base_sets}\n"
                f"Введите количество повторений:"
            )
        )
        await state.set_state(TrainingProcess.reps)
    else:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=bot_message_id)
        except Exception as e:
            logging.warning(f"Не удалось удалить сообщение бота: {e}")

        user_exercises = await orm_get_exercises(session, training_day_id)
        result_message = "Тренировка завершена, отличная работа!\n\nВаши результаты:\n"
        for exercise in user_exercises:
            result_message += f"\n<strong>Упражнение:</strong> {exercise.name}\n"
            sets = await orm_get_sets_by_session(session, exercise.id, training_session_id)
            if sets:
                for idx, user_set in enumerate(sets, start=1):
                    result_message += f"  Подход {idx}: {user_set.repetitions} повторений с весом {user_set.weight} кг\n"
            else:
                result_message += "  Нет данных о подходах.\n"
        bot_message = await message.answer(result_message)

        await state.clear()
        await state.update_data(bot_message_id=bot_message.message_id)
