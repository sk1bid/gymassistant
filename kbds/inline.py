from aiogram.types import InlineKeyboardButton
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder
import calendar
from datetime import date, timedelta

WEEK_DAYS = [calendar.day_abbr[i] for i in range(7)]
WEEK_DAYS_RU = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

MONTHS = [(i, calendar.month_name[i]) for i in range(1, 13)]


class MenuCallBack(CallbackData, prefix="menu"):
    level: int
    menu_name: str
    page: int = 1
    empty: bool = False
    training_day_id: int | None = None
    training_day_name: str | None = None
    exercise_id: int | None = None
    set_id: int | None = None
    program_id: int | None = None
    category_id: int | None = None
    year: int | None = None
    month: int | None = None


def get_user_main_btns(*, sizes: tuple[int] = (1,)):
    keyboard = InlineKeyboardBuilder()
    btns = {
        "🗓️ Расписание": "schedule",
        "⚙️ Программа тренировок": "program",
        "🙎🏻‍♂️ Профиль": "profile"
    }
    for text, menu_name in btns.items():
        keyboard.add(
            InlineKeyboardButton(
                text=text,
                callback_data=MenuCallBack(level=1, menu_name=menu_name).pack()
            )
        )

    return keyboard.adjust(*sizes).as_markup()


def get_user_programs_list(*, level: int, programs: list, active_program_id: int):
    keyboard = InlineKeyboardBuilder()

    for program in programs:
        if active_program_id == program.id:
            indicator = "🟢"
        else:
            indicator = "🔴"
        keyboard.add(
            InlineKeyboardButton(
                text=indicator + program.name,
                callback_data=MenuCallBack(level=level + 1, menu_name="program_" + program.name,
                                           program_id=program.id).pack()
            )
        )

    back_button = InlineKeyboardButton(
        text='⬅️ Назад',
        callback_data=MenuCallBack(level=level - 1, menu_name='main').pack()
    )
    add_program = InlineKeyboardButton(
        text='🆕 Добавить программу',
        callback_data="adding_program"
    )
    keyboard.row(back_button, add_program)
    return keyboard.as_markup()


def get_profile_btns(*, level: int, sizes: tuple[int] = (1,)):
    return InlineKeyboardBuilder().add(
        InlineKeyboardButton(
            text='⬅️ Назад',
            callback_data=MenuCallBack(level=level - 1, menu_name='main').pack()
        )
    ).adjust(*sizes).as_markup()


def get_schedule_btns(
    *,
    level: int,
    menu_name: str,
    year: int | None = None,
    month: int | None = None,
    training_day_id: int | None = None,
    first_exercise_id: int | None = None,
    active_program: bool | None = None,
    user_training_day_id: int | None = None,
    day_of_week_to_id: dict[str, int] | None = None  # Добавили этот параметр
):
    keyboard = InlineKeyboardBuilder()
    if active_program:
        today = date.today()
        MONTH_NAMES_RU = [
            "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
        ]

        # Проверяем, что year и month не None
        if year is None or month is None:
            year = today.year
            month = today.month

        month_year = f"{MONTH_NAMES_RU[month - 1]} {year}"
        month_header = InlineKeyboardButton(
            text=month_year,
            callback_data="month_header"
        )

        weekday_buttons = [
            InlineKeyboardButton(
                text=day_ru,
                callback_data=f"weekday_{day_ru}"
            )
            for day_ru in WEEK_DAYS_RU
        ]

        calendar_days = calendar.Calendar().monthdayscalendar(year=year, month=month)

        if menu_name == "schedule":
            keyboard.row(month_header)
            keyboard.row(*weekday_buttons)
            current_week = None
            if today.year == year and today.month == month:
                for week in calendar_days:
                    if today.day in week:
                        current_week = week
                        break
            if current_week is None:
                current_week = calendar_days[0]
            weeks_to_process = [current_week]
        elif menu_name.startswith("t_day"):
            weeks_to_process = None
        else:
            keyboard.row(month_header)
            keyboard.row(*weekday_buttons)
            weeks_to_process = calendar_days

        if weeks_to_process:
            for week_num, week in enumerate(weeks_to_process, start=1):
                week_buttons = []
                for day in week:
                    if day == 0:
                        week_buttons.append(
                            InlineKeyboardButton(text=' ', callback_data='empty')
                        )
                        continue

                    day_date = date(year, month, day)

                    # Определяем название дня
                    if day_date == today:
                        day_name = '🔘'
                    else:
                        day_name = str(day)

                    # Получаем индекс дня недели
                    day_of_week_index = day_date.weekday()
                    day_of_week_ru = WEEK_DAYS_RU[day_of_week_index].strip().lower()

                    # Используем переданный словарь для получения training_day_id
                    day_training_day_id = day_of_week_to_id.get(day_of_week_ru)

                    # Проверяем наличие training_day_id
                    if day_training_day_id is None:
                        # Если тренировочного дня нет, делаем кнопку неактивной или с другим callback_data
                        callback_data = 'no_training_day'
                    else:
                        callback_data = MenuCallBack(
                            level=level,
                            menu_name='t_day',
                            training_day_id=day_training_day_id
                        ).pack()

                    week_buttons.append(
                        InlineKeyboardButton(
                            text=day_name,
                            callback_data=callback_data
                        )
                    )
                keyboard.row(*week_buttons)

        # Остальная часть функции без изменений
        back_button = InlineKeyboardButton(
            text="Назад",
            callback_data=MenuCallBack(level=level - 1, menu_name='main').pack()
        )
        back_button_same_level = InlineKeyboardButton(
            text="Назад",
            callback_data=MenuCallBack(level=level, menu_name='schedule').pack()
        )

        start_training = InlineKeyboardButton(
            text="Начать тренировку",
            callback_data=MenuCallBack(
                level=level + 1,
                menu_name="training_process",
                training_day_id=training_day_id,
                exercise_id=first_exercise_id
            ).pack()
        )

        roll_up = InlineKeyboardButton(
            text="Свернуть календарь",
            callback_data=MenuCallBack(level=level, menu_name='schedule').pack()
        )

        unwrap = InlineKeyboardButton(
            text="Развернуть календарь",
            callback_data=MenuCallBack(level=level, menu_name='month_schedule').pack()
        )

        add_exercises = InlineKeyboardButton(
            text="Добавить упражнения",
            callback_data=MenuCallBack(
                level=4,
                menu_name="edit_trd",
                training_day_id=training_day_id
            ).pack()
        )

        if menu_name == "schedule":
            keyboard.row(back_button, unwrap)
        elif menu_name.startswith("t_day"):
            if first_exercise_id:
                keyboard.row(back_button_same_level, start_training)
            else:
                keyboard.row(back_button_same_level, add_exercises)
        else:
            keyboard.row(back_button, roll_up)
    else:
        back_button = InlineKeyboardButton(
            text="Назад",
            callback_data=MenuCallBack(level=level - 1, menu_name='main').pack()
        )
        add_program = InlineKeyboardButton(
            text="Добавить программу",
            callback_data=MenuCallBack(level=level, menu_name='program').pack()
        )
        keyboard.row(back_button, add_program)
    return keyboard.as_markup()



def get_training_process_btns(*, level: int, training_day_id: int):
    keyboard = InlineKeyboardBuilder()
    back_button = InlineKeyboardButton(
        text="Закончить тренировку",
        callback_data=MenuCallBack(level=level - 2, menu_name='finish_training', training_day_id=training_day_id).pack()
    )
    keyboard.row(back_button)
    return keyboard.as_markup()


def get_program_btns(*, level: int, sizes: tuple[int] = (2, 1), user_program_id: int):
    keyboard = InlineKeyboardBuilder()
    keyboard.add(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=MenuCallBack(level=level - 1, menu_name='program').pack()
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text='⚙️ Настройки',
            callback_data=MenuCallBack(level=level + 1, menu_name='prg_stg',
                                       program_id=user_program_id).pack()
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text='🔎 Тренировочные дни',
            callback_data=MenuCallBack(level=level + 1, menu_name='training_day',
                                       program_id=user_program_id).pack()
        )
    )

    return keyboard.adjust(*sizes).as_markup()


def get_program_stgs_btns(
        *,
        level: int,
        menu_name: str,
        user_program_id: int,
        active_program: bool,
        sizes: tuple[int] = (2, 1)
):
    keyboard = InlineKeyboardBuilder()
    if menu_name.startswith("to_del_prgm"):
        keyboard.add(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=MenuCallBack(level=level - 1, menu_name='show_program', program_id=user_program_id).pack()
            )
        )
        keyboard.add(
            InlineKeyboardButton(
                text="❌ Подтвердите удаление",
                callback_data=MenuCallBack(level=level - 2, menu_name="prgm_del", program_id=user_program_id).pack()
            )
        )
    else:

        keyboard.add(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=MenuCallBack(level=level - 1, menu_name='show_program', program_id=user_program_id).pack()
            )
        )

        keyboard.add(
            InlineKeyboardButton(
                text="❌ Удалить программу",
                callback_data=MenuCallBack(level=level, menu_name="to_del_prgm", program_id=user_program_id).pack()
            )
        )
        if active_program:
            keyboard.add(
                InlineKeyboardButton(
                    text="Отключить программу",
                    callback_data=MenuCallBack(level=level, menu_name="turn_off_prgm",
                                               program_id=user_program_id).pack()
                )
            )
        else:
            keyboard.add(
                InlineKeyboardButton(
                    text="Применить программу",
                    callback_data=MenuCallBack(level=level, menu_name="turn_on_prgm", program_id=user_program_id).pack()
                )
            )
    return keyboard.adjust(*sizes).as_markup()
    ####################################Тренировочные дни###########################################


def get_training_day_btns(
        *,
        level: int,
        user_program_id: int,
        training_day_id: int,
        page: int,
        pagination_btns: dict,
        program: list,
        sizes: tuple[int] = (2, 1)
):
    keyboard = InlineKeyboardBuilder()

    keyboard.add(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=MenuCallBack(level=level - 1, menu_name='show_program', program_id=user_program_id).pack()
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="✏️ Редактировать день",
            callback_data=MenuCallBack(
                level=level + 1,
                menu_name=f'trd_{program.name}',
                program_id=user_program_id,
                training_day_id=training_day_id,
                page=page
            ).pack()
        )
    )

    row = []
    for text, action in pagination_btns.items():
        row.append(
            InlineKeyboardButton(
                text=text,
                callback_data=MenuCallBack(
                    level=level,
                    menu_name=action,
                    program_id=user_program_id,
                    training_day_id=training_day_id,
                    page=page + 1 if action.startswith("next") else page - 1
                ).pack()
            )
        )

    if row:
        keyboard.row(*row)

    return keyboard.adjust(*sizes).as_markup()


def get_trd_edit_btns(
        *,
        level: int,
        menu_name: str,
        program_id: int,
        page: int,
        training_day_id: int,
        empty_list: bool,
        sizes: tuple[int] = (3, 1), ):
    keyboard = InlineKeyboardBuilder()
    back_callback = MenuCallBack(
        level=level - 1,
        menu_name='training_day',
        training_day_id=training_day_id,
        program_id=program_id,
        page=page
    ).pack()
    back_button = InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)
    keyboard.add(back_button)

    keyboard.add(
        InlineKeyboardButton(
            text="➕ Добавить упражнение",
            callback_data=MenuCallBack(
                level=level + 1,
                menu_name=f"ctg_{menu_name}",
                program_id=program_id,
                training_day_id=training_day_id,
                page=page
            ).pack()
        )
    )
    if not empty_list:
        keyboard.add(
            InlineKeyboardButton(
                text="✏️ Редактировать упражнение",
                callback_data=MenuCallBack(
                    level=level + 1,
                    menu_name="edit_excs",
                    program_id=program_id,
                    training_day_id=training_day_id,
                    page=page
                ).pack()
            )
        )

    return keyboard.adjust(*sizes).as_markup()


########################Категории и упражнения########################################

def get_category_btns(
        *,
        level: int,
        program_id: int,
        categories: list,
        page: int,
        training_day_id: int,
        sizes: tuple[int] = (3, 3),
):
    keyboard = InlineKeyboardBuilder()

    for category, count in categories:
        callback = MenuCallBack(
            menu_name=f"catg_{category.name}",
            level=level + 1,
            category_id=category.id,
            training_day_id=training_day_id,
            program_id=program_id,
            page=page
        ).pack()
        button_text = f"{category.name} ({count})"
        button = InlineKeyboardButton(text=button_text, callback_data=callback)
        keyboard.add(button)

    padding = (-len(categories)) % sizes[0]
    for _ in range(padding):
        keyboard.add(InlineKeyboardButton(text=" ", callback_data="empty"))

    back_callback = MenuCallBack(
        level=level - 1,
        menu_name='training_day',
        training_day_id=training_day_id,
        program_id=program_id,
        page=page
    ).pack()
    back_button = InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)
    keyboard.row(back_button)

    return keyboard.adjust(*sizes).as_markup()


def get_category_exercise_btns(
        *,
        level: int,
        program_id: int,
        template_exercises: list,
        page: int,
        training_day_id: int,
        menu_name: str,
        sizes: tuple[int] = (2, 2),
):
    keyboard = InlineKeyboardBuilder()
    for exercise in template_exercises:
        callback = MenuCallBack(
            menu_name=f"add_ex",
            level=level,
            exercise_id=exercise.id,
            category_id=exercise.category_id,
            training_day_id=training_day_id,
            program_id=program_id,
            page=page
        ).pack()
        button = InlineKeyboardButton(text=f"➕ {exercise.name}", callback_data=callback)
        keyboard.add(button)
    padding = (-len(template_exercises)) % sizes[0]
    for _ in range(padding):
        keyboard.add(InlineKeyboardButton(text=" ", callback_data="empty"))
    back_callback = MenuCallBack(
        level=level - 1,
        menu_name=menu_name.split("_")[-1],
        training_day_id=training_day_id,
        program_id=program_id,
        page=page
    ).pack()
    back_button = InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)
    keyboard.row(back_button)
    return keyboard.adjust(*sizes).as_markup()


#######################################Изменение упражнения###############################

def get_edit_exercise_btns(
        *,
        level: int,
        program_id: int,
        user_exercises: list,
        page: int,
        exercise_id: int | None,
        training_day_id: int,
        menu_name: str
):
    keyboard = InlineKeyboardBuilder()

    if menu_name.startswith("to_edit"):
        # Добавляем кнопки упражнений
        for exercise in user_exercises:
            if exercise_id == exercise.id:
                button_text = f"👉 {exercise.name}"
            else:
                button_text = f"🔘 {exercise.name}"

            # Создаём кнопку упражнения
            exercise_button = InlineKeyboardButton(
                text=button_text,
                callback_data=MenuCallBack(
                    menu_name=f"to_edit",
                    level=level,
                    exercise_id=exercise.id,
                    page=page,
                    training_day_id=training_day_id,
                    program_id=program_id,
                ).pack()
            )
            keyboard.row(exercise_button)

        if exercise_id is not None:

            delete_callback = MenuCallBack(
                menu_name="del",
                level=level if len(user_exercises) != 1 else level - 1,
                exercise_id=exercise_id,
                page=page,
                training_day_id=training_day_id,
                program_id=program_id,
            ).pack()

            delete_button = InlineKeyboardButton(
                text="🗑️ Удалить упражнение",
                callback_data=delete_callback
            )

            back_callback = MenuCallBack(
                level=level - 1,
                menu_name="trd",
                training_day_id=training_day_id,
                program_id=program_id,
                page=page
            ).pack()
            mv_up_callback = MenuCallBack(
                menu_name="mv_up",
                level=level,
                exercise_id=exercise_id,
                page=page,
                training_day_id=training_day_id,
                program_id=program_id,
            ).pack()

            mvup_button = InlineKeyboardButton(text="⬆️", callback_data=mv_up_callback)

            # Кнопка для перемещения вниз
            mv_down_callback = MenuCallBack(
                menu_name="mv_down",
                level=level,
                exercise_id=exercise_id,
                page=page,
                training_day_id=training_day_id,
                program_id=program_id,
            ).pack()

            mvdown_button = InlineKeyboardButton(text="⬇️", callback_data=mv_down_callback)
            back_button = InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=back_callback
            )

            settings_callback = MenuCallBack(
                menu_name="ex_setgs",
                level=level + 1,
                exercise_id=exercise_id,
                page=page,
                training_day_id=training_day_id,
                program_id=program_id,
            ).pack()

            settings_button = InlineKeyboardButton(text="⚙️ Настройки", callback_data=settings_callback)

            keyboard.row(mvdown_button, mvup_button, delete_button)
            keyboard.row(back_button, settings_button)
        else:

            back_callback = MenuCallBack(
                level=level - 1,
                menu_name="trd",
                training_day_id=training_day_id,
                program_id=program_id,
                page=page
            ).pack()

            back_button = InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=back_callback
            )

            keyboard.row(back_button)
    else:

        for exercise in user_exercises:
            exercise_button = InlineKeyboardButton(
                text=f"🔘 {exercise.name}",
                callback_data=MenuCallBack(
                    menu_name=f"to_edit",
                    level=level,
                    exercise_id=exercise.id,
                    page=page,
                    training_day_id=training_day_id,
                    program_id=program_id,
                ).pack()
            )
            keyboard.row(exercise_button)

        back_callback = MenuCallBack(
            level=level - 1,
            menu_name="trd",
            training_day_id=training_day_id,
            program_id=program_id,
            page=page
        ).pack()

        back_button = InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=back_callback
        )

        keyboard.row(back_button)
    return keyboard.as_markup()


def incr_reduce_sets_reps(level: int, page: int, exercise_id: int, training_day_id: int, program_id: int, amount: int,
                          operation: str, tp: str, set_id: int):
    return InlineKeyboardButton(
        text=f"{operation}{amount}",
        callback_data=MenuCallBack(
            menu_name=f"{operation}_{amount}_{tp}_{set_id}",
            level=level,
            exercise_id=exercise_id,
            page=page,
            training_day_id=training_day_id,
            program_id=program_id,
        ).pack())


def get_exercise_settings_btns(
        *,
        level: int,
        menu_name: str,
        program_id: int,
        user_exercise: list,
        base_ex_sets: list,
        page: int,
        exercise_id: int | None,
        training_day_id: int,

):
    keyboard = InlineKeyboardBuilder()
    empty_callback = MenuCallBack(level=level, menu_name=menu_name, empty=True, exercise_id=exercise_id,
                                  page=page,
                                  training_day_id=training_day_id,
                                  program_id=program_id).pack()
    exercise = InlineKeyboardButton(
        text=f"🔘 {user_exercise.name}",
        callback_data=empty_callback)
    keyboard.row(exercise)

    set_increase_1 = incr_reduce_sets_reps(level, page, exercise_id, training_day_id, program_id,
                                           1, "➕", "sets", -1)

    set_reduce_1 = incr_reduce_sets_reps(level, page, exercise_id, training_day_id, program_id,
                                         1, "➖", "sets", -1)

    back_callback = MenuCallBack(
        level=level - 1,
        menu_name="edit_excs",
        training_day_id=training_day_id,
        program_id=program_id,
        page=page
    ).pack()

    back_button = InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data=back_callback
    )

    for index, exercise_set in enumerate(base_ex_sets, 1):
        reps = InlineKeyboardButton(
            text=f"Reps: {exercise_set.reps}",
            callback_data=empty_callback)
        sets = InlineKeyboardButton(
            text=f"Подход {index}",
            callback_data=empty_callback)

        rep_increase_1 = incr_reduce_sets_reps(level, page, exercise_id, training_day_id, program_id,
                                               1, "➕", "reps", exercise_set.id)

        rep_reduce_1 = incr_reduce_sets_reps(level, page, exercise_id, training_day_id, program_id,
                                             1, "➖", "reps", exercise_set.id)
        keyboard.row(sets, reps, rep_reduce_1, rep_increase_1)

    set_amount = InlineKeyboardButton(
        text=f"Sets: {len(base_ex_sets)}",
        callback_data=empty_callback)
    keyboard.row(back_button, set_amount, set_reduce_1, set_increase_1)
    return keyboard.as_markup()


######################################Базовые функции####################################
def get_callback_btns(
        *,
        btns: dict[str, str],
        sizes: tuple[int] = (2,),
):
    keyboard = InlineKeyboardBuilder()

    for text, data in btns.items():
        keyboard.add(
            InlineKeyboardButton(
                text=text,
                callback_data=data
            )
        )

    return keyboard.adjust(*sizes).as_markup()


def get_url_btns(
        *,
        btns: dict[str, str],
        sizes: tuple[int] = (2,),
):
    keyboard = InlineKeyboardBuilder()

    for text, url in btns.items():
        keyboard.add(
            InlineKeyboardButton(
                text=text,
                url=url
            )
        )

    return keyboard.adjust(*sizes).as_markup()


def get_inlineMix_btns(
        *,
        btns: dict[str, str],
        sizes: tuple[int] = (2,),
):
    keyboard = InlineKeyboardBuilder()

    for text, value in btns.items():
        if '://' in value:
            keyboard.add(
                InlineKeyboardButton(
                    text=text,
                    url=value
                )
            )
        else:
            keyboard.add(
                InlineKeyboardButton(
                    text=text,
                    callback_data=value
                )
            )

    return keyboard.adjust(*sizes).as_markup()
