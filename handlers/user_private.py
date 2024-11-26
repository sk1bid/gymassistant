import asyncio
import uuid

from asyncio import sleep
import time
import logging
from datetime import datetime

from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from sqlalchemy.ext.asyncio import AsyncSession
from database.orm_query import (
    orm_add_user,
    orm_update_user,
    orm_add_program,
    orm_get_user_by_id,
    orm_get_program,
    orm_get_training_day,
    orm_get_exercises,
    orm_update_program,
    orm_delete_exercise,
    orm_update_exercise,
    move_exercise_down,
    move_exercise_up,
    orm_delete_program,
    orm_get_exercise,
    orm_update_exercise_set,
    orm_delete_exercise_set,
    orm_add_exercise_set,
    orm_get_exercise_set,
    orm_get_exercise_sets,
    orm_add_set,
    orm_update_set,
    orm_get_set,
    orm_get_sets, orm_turn_on_off_program, orm_get_programs, orm_get_sets_by_session,
)

from handlers.menu_processing import get_menu_content
from kbds.inline import MenuCallBack, get_callback_btns

user_private_router = Router()
user_private_router.message.filter(F.chat.type == "private")


class AddUser(StatesGroup):
    user_id = State()
    name = State()
    weight = State()

    user_for_change = None

    texts = {
        "AddUser:name": "Введите ваше имя заново:",
        "AddUser:weight": "Введите ваш вес заново:",
    }


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


@user_private_router.message(StateFilter(None), CommandStart())
async def send_welcome(message: types.Message, state: FSMContext, session: AsyncSession):
    start_time = time.monotonic()

    user_id = message.from_user.id

    try:
        user = await orm_get_user_by_id(session, user_id)

        if user:
            await message.answer(f"Вы уже зарегистрированы как {user.name}.")
            media, reply_markup = await get_menu_content(session, level=0, menu_name="main")
            await message.answer_photo(photo=media.media, caption=media.caption, reply_markup=reply_markup)
        else:
            await message.answer("Привет, я твой виртуальный тренер. Давай тебя зарегистрируем. Напиши свое имя:")
            await state.set_state(AddUser.name)
            await state.update_data(user_id=int(user_id))

    except Exception as e:
        logging.exception(f"Ошибка в send_welcome: {e}")
        await message.answer("Произошла ошибка, попробуйте позже.")

    finally:
        end_time = time.monotonic()
        duration = end_time - start_time
        logging.info(f"Обработка send_welcome заняла {duration:.2f} секунд")


@user_private_router.message(
    StateFilter(AddUser.name.state, AddUser.weight.state, AddTrainingProgram.name.state),
    Command("отмена")
)
@user_private_router.message(
    StateFilter(AddUser.name.state, AddUser.weight.state, AddTrainingProgram.name.state),
    F.text.casefold() == "отмена"
)
async def cancel_handler(message: types.Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state is None:
        return

    await state.clear()
    await message.answer("Действия отменены")


@user_private_router.message(
    StateFilter(AddUser.name.state, AddUser.weight.state),
    Command("назад")
)
@user_private_router.message(
    StateFilter(AddUser.name.state, AddUser.weight.state),
    F.text.casefold() == "назад"
)
async def back_step_handler(message: types.Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    logging.info(f"Текущее состояние: {current_state}")

    if current_state == AddUser.name.state:
        await message.answer('Предыдущего шага нет, введите ваше имя или напишите "отмена"')
        return

    previous_state = None
    for step in AddUser.__all_states__:
        if step.state == current_state:
            if previous_state:
                await state.set_state(previous_state)
                await message.answer(f"Ок, вы вернулись к прошлому шагу\n{AddUser.texts.get(previous_state, '')}")
            else:
                await message.answer("Вы находитесь на первом шаге.")
            return
        previous_state = step.state


@user_private_router.message(AddUser.name, F.text)
async def add_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer(f"Отлично, {message.text}. Введите ваш вес:")
    await state.set_state(AddUser.weight)


@user_private_router.message(AddUser.weight, F.text)
async def add_weight(message: types.Message, state: FSMContext, session: AsyncSession):
    try:
        weight = float(message.text)
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
    except Exception as e:
        logging.exception(f"Ошибка при добавлении пользователя: {e}")
        await message.answer(f"Ошибка: \n{str(e)}\nОбратитесь к администратору.")
        await state.clear()

    media, reply_markup = await get_menu_content(session, level=0, menu_name="main")
    await message.answer_photo(photo=media.media, caption=media.caption, reply_markup=reply_markup)


#################################### FSM для добавления тренировочной программы ####################################

@user_private_router.callback_query(StateFilter(None), F.data == "adding_program")
async def ask_name(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите название программы тренировок:")
    await state.set_state(AddTrainingProgram.name)
    await callback.answer()


@user_private_router.message(AddTrainingProgram.name, F.text)
async def add_training_program_name(message: types.Message, state: FSMContext, session: AsyncSession):
    start_time = time.monotonic()

    user_id = message.from_user.id

    if len(message.text) > 15:
        await message.answer("Пожалуйста, введите название короче 15 символов:")
        return

    await state.update_data(user_id=user_id, name=message.text)
    data = await state.get_data()
    user_data = await orm_get_user_by_id(session, message.from_user.id)

    try:
        training_program_for_change = data.get('training_program_for_change')
        if training_program_for_change:
            await orm_update_program(session, training_program_for_change.id, data)
        else:
            await orm_add_program(session, data)
            if not user_data.actual_program_id:
                user_programs = await orm_get_programs(session, user_id)
                await orm_turn_on_off_program(session, user_id, user_programs[-1].id)
    except Exception as e:
        logging.exception(f"Ошибка при добавлении программы: {e}")
        await message.answer(f"Ошибка: \n{str(e)}\nОбратитесь к администратору.")
        await state.clear()
        return

    await message.answer("Готово!")
    media, reply_markup = await get_menu_content(session, level=1, menu_name="program", user_id=user_id)
    await message.answer_photo(photo=media.media, caption=media.caption, reply_markup=reply_markup)
    await state.clear()

    end_time = time.monotonic()
    duration = end_time - start_time
    logging.info(f"Обработка add_training_program_name заняла {duration:.2f} секунд")


###########################################################################################

async def clicked_btn(callback_data: MenuCallBack, state: FSMContext, selected_id, callback: types.CallbackQuery,
                      session: AsyncSession, clicked_id):
    new_selected_id = None if selected_id == clicked_id else clicked_id
    if callback_data.menu_name.startswith("to_edit"):
        await state.update_data(selected_exercise_id=new_selected_id)
    elif callback_data.menu_name == "to_del_prgm":
        await state.update_data(selected_program_id=new_selected_id)

    media, reply_markup = await get_menu_content(
        session,
        level=callback_data.level,
        menu_name=callback_data.menu_name,
        training_program_id=callback_data.program_id,
        exercise_id=new_selected_id,
        page=callback_data.page,
        training_day_id=callback_data.training_day_id,
        user_id=callback.from_user.id,
        category_id=callback_data.category_id
    )

    await callback.message.edit_media(media=media, reply_markup=reply_markup)
    await callback.answer()


########################################################################################################################

@user_private_router.callback_query(MenuCallBack.filter())
async def user_menu(callback: types.CallbackQuery, callback_data: MenuCallBack, session: AsyncSession,
                    state: FSMContext):
    start_time = time.monotonic()

    try:

        logging.info(f"Получен callback от пользователя {callback.from_user.id}: {callback_data}")

        user_data = await state.get_data()
        selected_exercise_id = user_data.get("selected_exercise_id")
        selected_program_id = user_data.get("selected_program_id")

        if callback_data.menu_name.startswith("to_edit"):
            await clicked_btn(session=session, callback_data=callback_data, state=state,
                              selected_id=selected_exercise_id,
                              callback=callback, clicked_id=callback_data.exercise_id)

        elif callback_data.menu_name.startswith("del"):
            await orm_delete_exercise(session, callback_data.exercise_id)
            await state.update_data(selected_exercise_id=None)

            media, reply_markup = await get_menu_content(
                session,
                level=callback_data.level,
                menu_name="to_edit",
                training_program_id=callback_data.program_id,
                exercise_id=None,
                page=callback_data.page,
                training_day_id=callback_data.training_day_id,
                user_id=callback.from_user.id,
                category_id=callback_data.category_id,
                year=callback_data.year,
                month=callback_data.month,
            )

            await callback.message.edit_media(media=media, reply_markup=reply_markup)
            await callback.answer("Упражнение удалено.")

        elif callback_data.menu_name.startswith("mv"):
            if callback_data.menu_name == "mv_up":
                await callback.answer(await move_exercise_up(session, callback_data.exercise_id))
            elif callback_data.menu_name == "mv_down":
                await callback.answer(await move_exercise_down(session, callback_data.exercise_id))

            media, reply_markup = await get_menu_content(
                session,
                level=callback_data.level,
                menu_name="to_edit",
                training_program_id=callback_data.program_id,
                exercise_id=callback_data.exercise_id,
                page=callback_data.page,
                training_day_id=callback_data.training_day_id,
                user_id=callback.from_user.id,
                category_id=callback_data.category_id,
                year=callback_data.year,
                month=callback_data.month,
            )

            await callback.message.edit_media(media=media, reply_markup=reply_markup)
            await callback.answer()

        elif callback_data.menu_name == "to_del_prgm":
            await clicked_btn(session=session, callback_data=callback_data, state=state,
                              selected_id=selected_program_id,
                              callback=callback, clicked_id=callback_data.program_id)

        elif callback_data.menu_name == "prgm_del":
            await orm_delete_program(session, callback_data.program_id)
            await orm_turn_on_off_program(session, callback.message.from_user.id, None)
            await state.update_data(selected_program_id=None)

            media, reply_markup = await get_menu_content(
                session,
                level=callback_data.level,
                menu_name="program",
                training_program_id=None,
                exercise_id=None,
                page=callback_data.page,
                training_day_id=callback_data.training_day_id,
                user_id=callback.from_user.id,
                category_id=callback_data.category_id,
                year=callback_data.year,
                month=callback_data.month,
            )

            await callback.message.edit_media(media=media, reply_markup=reply_markup)
            await callback.answer("Программа удалена.")

        elif callback_data.menu_name.startswith("➕") or callback_data.menu_name.startswith("➖"):
            user_exercise = await orm_get_exercise(session, callback_data.exercise_id)
            increment = int(callback_data.menu_name.split("_")[1])
            field = callback_data.menu_name.split("_")[2]
            operation = callback_data.menu_name[0]
            set_id = int(callback_data.menu_name.split("_")[3])
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
                menu_name=f"{operation}_{field}",
                training_program_id=callback_data.program_id,
                exercise_id=callback_data.exercise_id,
                page=callback_data.page,
                training_day_id=callback_data.training_day_id,
                user_id=callback.from_user.id,
                category_id=callback_data.category_id,
                year=callback_data.year,
                month=callback_data.month,
            )

            await callback.message.edit_media(media=media, reply_markup=reply_markup)
            await callback.answer()

        elif callback_data.menu_name == "training_process":
            media, reply_markup = await get_menu_content(
                session,
                level=callback_data.level,
                menu_name=callback_data.menu_name,
                training_program_id=callback_data.program_id,
                exercise_id=callback_data.exercise_id,
                page=callback_data.page,
                training_day_id=callback_data.training_day_id,
                user_id=callback.from_user.id,
                category_id=callback_data.category_id,
                year=callback_data.year,
                month=callback_data.month,
            )

            await callback.message.edit_media(media=media, reply_markup=reply_markup)

            await callback.answer()

            await handle_start_training_process(callback, callback_data, state, session)
        elif callback_data.menu_name == "finish_training":
            try:
                await callback.answer()
                media, reply_markup = await get_menu_content(
                    session,
                    level=callback_data.level,
                    menu_name=callback_data.menu_name,
                    training_program_id=callback_data.program_id,
                    exercise_id=callback_data.exercise_id,
                    page=callback_data.page,
                    training_day_id=callback_data.training_day_id,
                    user_id=callback.from_user.id,
                    category_id=callback_data.category_id,
                    year=callback_data.year,
                    month=callback_data.month,
                )
                await callback.message.edit_media(media=media, reply_markup=reply_markup)
                bot_message_id = user_data.get('bot_message_id')
                await callback.message.bot.delete_message(chat_id=callback.message.chat.id, message_id=bot_message_id)
                await state.clear()
            except Exception as e:
                logging.warning(f"Не удалось удалить сообщение бота: {e}")

        else:
            media, reply_markup = await get_menu_content(
                session,
                level=callback_data.level,
                menu_name=callback_data.menu_name,
                training_program_id=callback_data.program_id,
                exercise_id=callback_data.exercise_id,
                page=callback_data.page,
                training_day_id=callback_data.training_day_id,
                user_id=callback.from_user.id,
                category_id=callback_data.category_id,
                year=callback_data.year,
                month=callback_data.month,
            )
            await state.update_data(selected_exercise_id=None, selected_program_id=None)
            await callback.message.edit_media(media=media, reply_markup=reply_markup)
            await callback.answer()
    except Exception as e:
        logging.exception(f"Ошибка в обработчике user_menu: {e}")
        await callback.answer("Произошла ошибка, попробуйте позже.")

    finally:
        end_time = time.monotonic()
        duration = end_time - start_time
        logging.info(f"Обработка user_menu заняла {duration:.2f} секунд")


async def handle_start_training_process(callback, callback_data, state, session):
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

    # Добавляем клавиатуру с кнопкой "Закончить тренировку"
    bot_msg = await callback.message.answer(
        f"Начинаем тренировку!\n\nУпражнение: {current_exercise.name}\n{current_exercise.description}\n\n"
        f"Подход 1 из {current_exercise.base_sets}\nВведите количество повторений:"
    )
    await state.update_data(bot_message_id=bot_msg.message_id)
    await state.set_state(TrainingProcess.reps)
    await callback.answer()


# Обработчик для начала процесса тренировки
@user_private_router.callback_query(MenuCallBack.filter(F.menu_name == "training_process"))
async def start_training_process(callback: types.CallbackQuery, callback_data: MenuCallBack, state: FSMContext,
                                 session: AsyncSession):
    await handle_start_training_process(callback, callback_data, state, session)


# Обработчик для ввода количества повторений
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

    # Удаляем сообщение пользователя после обработки
    try:
        await message.delete()
    except Exception as e:
        logging.warning(f"Не удалось удалить сообщение пользователя: {e}")

    data = await state.get_data()
    bot_message_id = data.get('bot_message_id')

    # Обновляем сообщение бота
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

    # Удаляем сообщение пользователя
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

        # Обновляем сообщение бота для следующего подхода
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
    training_session_id = data.get('training_session_id')  # Получаем training_session_id

    if exercise_index < len(exercise_ids):
        await state.update_data(
            exercise_index=exercise_index,
            current_exercise_id=exercise_ids[exercise_index],
            set_index=1
        )

        current_exercise = await orm_get_exercise(session, exercise_ids[exercise_index])

        # Обновляем сообщение бота для следующего упражнения
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
        # Тренировка завершена, удаляем сообщение бота
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=bot_message_id)
        except Exception as e:
            logging.warning(f"Не удалось удалить сообщение бота: {e}")

        # Получаем упражнения текущего тренировочного дня
        user_exercises = await orm_get_exercises(session, training_day_id)

        # Формируем результаты тренировки
        result_message = "Тренировка завершена, отличная работа!\n\nВаши результаты:\n"

        for exercise in user_exercises:
            result_message += f"\n<strong>Упражнение:</strong> {exercise.name}\n"
            # Получаем сеты текущей тренировочной сессии для данного упражнения
            sets = await orm_get_sets_by_session(session, exercise.id, training_session_id)
            if sets:
                for idx, user_set in enumerate(sets, start=1):
                    result_message += (
                        f"  Подход {idx}: {user_set.repetitions} повторений с весом {user_set.weight} кг\n"
                    )
            else:
                result_message += "  Нет данных о подходах.\n"
        bot_message = await message.answer(result_message)

        # Очищаем состояние после завершения тренировки
        await state.clear()
        await state.update_data(bot_message_id=bot_message.message_id)
