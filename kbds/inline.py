import calendar
from datetime import date

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder

from utils.separator import get_action_part

WEEK_DAYS = [calendar.day_abbr[i] for i in range(7)]
WEEK_DAYS_RU = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]

MONTHS = [(i, calendar.month_name[i]) for i in range(1, 13)]

# Константы для часто используемых «магических» значений
ADDING_PROGRAM = "adding_program"
EMPTY_CALLBACK = "empty"
NO_TRAINING_DAY = "no_training_day"
MONTH_HEADER = "month_header"


class MenuCallBack(CallbackData, prefix="menu"):
    """CallbackData для FSM с унифицированными полями."""
    level: int
    action: str
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


def error_btns() -> InlineKeyboardMarkup:
    """
    Возвращает клавиатуру с кнопками для возврата в главное меню или обращения к разработчику.
    """
    keyboard = InlineKeyboardBuilder()
    keyboard.add(
        InlineKeyboardButton(
            text="🏠 Вернуться в главное меню",
            callback_data=MenuCallBack(level=0, action="main").pack()
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="🪳 Написать разработчику",
            url="https://t.me/cg_skbid")
    )
    return keyboard.as_markup()


def get_user_main_btns(*, sizes: tuple[int] = (1,)) -> InlineKeyboardMarkup:
    """
    Возвращает клавиатуру главного меню пользователя.
    Кнопки: Расписание, Программа тренировок, Профиль.
    """
    keyboard = InlineKeyboardBuilder()
    btns = {
        "🗓️ Расписание": "schedule",
        "⚙️ Программа тренировок": "program",
        "🙎🏻‍♂️ Профиль": "profile"
    }
    for text, action in btns.items():
        keyboard.add(
            InlineKeyboardButton(
                text=text,
                callback_data=MenuCallBack(level=1, action=action).pack()
            )
        )
    return keyboard.adjust(*sizes).as_markup()


def get_user_programs_list(*, level: int, programs: list, active_program_id: int,
                           sizes: tuple[int] = (2, 2)) -> InlineKeyboardMarkup:
    """
    Возвращает клавиатуру со списком программ пользователя.
    Активная программа помечается зеленым индикатором, неактивные — красным.
    """
    keyboard = InlineKeyboardBuilder()
    for program in programs:
        indicator = "🟢" if active_program_id == program.id else "🔴"
        keyboard.row(
            InlineKeyboardButton(
                text=indicator + " " + program.name,
                callback_data=MenuCallBack(level=level + 1, action=f"program_{program.name}",
                                           program_id=program.id).pack()
            )
        )
    padding = (-len(programs)) % sizes[0]
    if len(programs) >= 2:
        for _ in range(padding):
            keyboard.add(InlineKeyboardButton(text=" ", callback_data=EMPTY_CALLBACK))
    if len(programs) == 1:
        sizes = (1, 2)
    back_button = InlineKeyboardButton(
        text='⬅️ Назад',
        callback_data=MenuCallBack(level=level - 1, action='main').pack()
    )
    add_program = InlineKeyboardButton(
        text='🆕 Добавить программу',
        callback_data=ADDING_PROGRAM
    )
    keyboard.row(back_button, add_program)
    return keyboard.adjust(*sizes).as_markup()


def get_profile_btns(*, level: int, sizes: tuple[int] = (1,)) -> InlineKeyboardMarkup:
    """
    Возвращает клавиатуру профиля с кнопкой возврата назад.
    """
    return InlineKeyboardBuilder().add(
        InlineKeyboardButton(
            text='⬅️ Назад',
            callback_data=MenuCallBack(level=level - 1, action='main').pack()
        )
    ).adjust(*sizes).as_markup()


def get_schedule_btns(
        *,
        level: int,
        action: str,
        year: int | None = None,
        month: int | None = None,
        training_day_id: int | None = None,
        first_exercise_id: int | None = None,
        active_program: int | None = None,
        day_of_week_to_id: dict[str, int] | None = None
) -> InlineKeyboardMarkup:
    """
    Возвращает клавиатуру для отображения расписания.
    В зависимости от action, может быть свернутый или развернутый вид.
    При наличии active_program формируется календарь, иначе – кнопка добавить программу.
    """
    keyboard = InlineKeyboardBuilder()
    if active_program:
        today = date.today()
        MONTH_NAMES_RU = [
            "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
        ]

        if year is None or month is None:
            year = today.year
            month = today.month

        month_year = f"{MONTH_NAMES_RU[month - 1]} {year}"
        month_header = InlineKeyboardButton(
            text=month_year,
            callback_data=MONTH_HEADER
        )

        weekday_buttons = [
            InlineKeyboardButton(
                text=day_ru,
                callback_data=f"weekday_{day_ru}"
            )
            for day_ru in WEEK_DAYS_RU
        ]

        calendar_days = calendar.Calendar().monthdayscalendar(year=year, month=month)

        if action == "schedule":
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
        elif action.startswith("t_day"):
            weeks_to_process = None
        else:
            # month_schedule или другой режим
            keyboard.row(month_header)
            keyboard.row(*weekday_buttons)
            weeks_to_process = calendar_days

        if weeks_to_process:
            for week in weeks_to_process:
                week_buttons = []
                for day in week:
                    if day == 0:
                        week_buttons.append(
                            InlineKeyboardButton(text=' ', callback_data=EMPTY_CALLBACK)
                        )
                        continue

                    day_date = date(year, month, day)
                    day_name = '🔘' if day_date == today else str(day)
                    day_of_week_index = day_date.weekday()
                    day_of_week_ru = WEEK_DAYS_RU[day_of_week_index].strip().lower()

                    day_training_day_id = day_of_week_to_id.get(day_of_week_ru)
                    if day_training_day_id is None:
                        callback_data = NO_TRAINING_DAY
                    else:
                        callback_data = MenuCallBack(
                            level=level,
                            action='t_day',
                            training_day_id=day_training_day_id
                        ).pack()

                    week_buttons.append(
                        InlineKeyboardButton(
                            text=day_name,
                            callback_data=callback_data
                        )
                    )
                keyboard.row(*week_buttons)

        back_button = InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=MenuCallBack(level=level - 1, action='main').pack()
        )
        back_button_same_level = InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=MenuCallBack(level=level, action='schedule').pack()
        )

        start_training = InlineKeyboardButton(
            text="💪 Начать тренировку",
            callback_data=MenuCallBack(
                level=level + 1,
                action="training_process",
                training_day_id=training_day_id,
                exercise_id=first_exercise_id
            ).pack()
        )

        roll_up = InlineKeyboardButton(
            text="🔽 Свернуть календарь",
            callback_data=MenuCallBack(level=level, action='schedule').pack()
        )

        unwrap = InlineKeyboardButton(
            text="⏏ Развернуть календарь",
            callback_data=MenuCallBack(level=level, action='month_schedule').pack()
        )

        add_exercises = InlineKeyboardButton(
            text="➕ Добавить упражнения",
            callback_data=MenuCallBack(
                level=4,
                action="shd/edit_trd",
                training_day_id=training_day_id,
                program_id=active_program,
            ).pack()
        )
        edit_t_day = InlineKeyboardButton(
            text="✏️ Редактировать день",
            callback_data=MenuCallBack(
                level=4,
                action="shd/edit_trd",
                training_day_id=training_day_id,
                program_id=active_program,
            ).pack()
        )

        if action == "schedule":
            if first_exercise_id:
                keyboard.row(start_training)
            else:
                keyboard.row(add_exercises)
            keyboard.row(back_button, unwrap)
        elif action.startswith("t_day"):
            if first_exercise_id:
                keyboard.row(start_training)
                keyboard.row(back_button_same_level, edit_t_day)
            else:
                keyboard.row(back_button_same_level, add_exercises)
        else:
            # month_schedule
            if first_exercise_id:
                keyboard.row(start_training, edit_t_day)
            else:
                keyboard.row(add_exercises)
            keyboard.row(back_button, roll_up)
    else:
        back_button = InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=MenuCallBack(level=level - 1, action='main').pack()
        )
        add_program = InlineKeyboardButton(
            text="➕ Добавить программу",
            callback_data=MenuCallBack(level=level, action='program').pack()
        )
        keyboard.row(back_button, add_program)
    return keyboard.as_markup()


def get_training_process_btns(*, level: int, training_day_id: int) -> InlineKeyboardMarkup:
    """
    Возвращает клавиатуру процесса тренировки с кнопкой завершения.
    """
    keyboard = InlineKeyboardBuilder()
    back_button = InlineKeyboardButton(
        text="🏁 Закончить тренировку",
        callback_data=MenuCallBack(level=level - 2, action='finish_training', training_day_id=training_day_id).pack()
    )
    keyboard.row(back_button)
    return keyboard.as_markup()


def get_program_btns(*, level: int, sizes: tuple[int] = (2, 1), user_program_id: int) -> InlineKeyboardMarkup:
    """
    Возвращает клавиатуру настроек программы.
    """
    keyboard = InlineKeyboardBuilder()
    keyboard.add(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=MenuCallBack(level=level - 1, action='program').pack()
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text='⚙️ Настройки',
            callback_data=MenuCallBack(level=level + 1, action='prg_stg', program_id=user_program_id).pack()
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text='🔎 Тренировочные дни',
            callback_data=MenuCallBack(level=level + 1, action='training_day', program_id=user_program_id).pack()
        )
    )
    return keyboard.adjust(*sizes).as_markup()


def get_program_stgs_btns(
        *,
        level: int,
        action: str,
        user_program_id: int,
        active_program: bool,
        sizes: tuple[int] = (2, 1)
) -> InlineKeyboardMarkup:
    """
    Возвращает клавиатуру настроек конкретной программы:
    - Подтверждение удаления программы
    - Включение/отключение программы
    """
    keyboard = InlineKeyboardBuilder()
    if action.startswith("to_del_prgm"):
        keyboard.add(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=MenuCallBack(level=level - 1, action='show_program', program_id=user_program_id).pack()
            )
        )
        keyboard.add(
            InlineKeyboardButton(
                text="❌ Подтвердите удаление",
                callback_data=MenuCallBack(level=level - 2, action="prm_del", program_id=user_program_id).pack()
            )
        )
    else:
        keyboard.add(
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data=MenuCallBack(level=level - 1, action='show_program', program_id=user_program_id).pack()
            )
        )

        keyboard.add(
            InlineKeyboardButton(
                text="❌ Удалить программу",
                callback_data=MenuCallBack(level=level, action="to_del_prgm", program_id=user_program_id).pack()
            )
        )

        if active_program:
            keyboard.add(
                InlineKeyboardButton(
                    text="⭕ Отключить программу",
                    callback_data=MenuCallBack(level=level, action="turn_off_prgm", program_id=user_program_id).pack()
                )
            )
        else:
            keyboard.add(
                InlineKeyboardButton(
                    text="✅ Применить программу",
                    callback_data=MenuCallBack(level=level, action="turn_on_prgm", program_id=user_program_id).pack()
                )
            )
    return keyboard.adjust(*sizes).as_markup()


def get_training_day_btns(
        *,
        level: int,
        user_program_id: int,
        training_day_id: int,
        page: int,
        pagination_btns: dict,
        program: list,
        sizes: tuple[int] = (2, 1)
) -> InlineKeyboardMarkup:
    """
    Возвращает клавиатуру для конкретного тренировочного дня с кнопкой редактирования и пагинацией.
    """
    keyboard = InlineKeyboardBuilder()

    keyboard.add(
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=MenuCallBack(level=level - 1, action='show_program', program_id=user_program_id).pack()
        )
    )
    keyboard.add(
        InlineKeyboardButton(
            text="✏️ Редактировать день",
            callback_data=MenuCallBack(
                level=level + 1,
                action=f'edit_trd',
                program_id=user_program_id,
                training_day_id=training_day_id,
                page=page
            ).pack()
        )
    )

    row = []
    for text, act in pagination_btns.items():
        row.append(
            InlineKeyboardButton(
                text=text,
                callback_data=MenuCallBack(
                    level=level,
                    action=act,
                    program_id=user_program_id,
                    training_day_id=training_day_id,
                    page=page + 1 if act.startswith("next") else page - 1
                ).pack()
            )
        )

    if row:
        keyboard.row(*row)

    return keyboard.adjust(*sizes).as_markup()


def get_trd_edit_btns(
        *,
        level: int,
        action: str,
        program_id: int,
        page: int,
        training_day_id: int,
        empty_list: bool,
        sizes: tuple[int] = (3, 1),
) -> InlineKeyboardMarkup:
    """
    Возвращает клавиатуру редактирования тренировочного дня с кнопками назад и добавления упражнения.
    Если список упражнений пуст — кнопка редактирования отсутствует.
    """
    keyboard = InlineKeyboardBuilder()
    back_callback = MenuCallBack(
        level=level - 1,
        action='training_day',
        training_day_id=training_day_id,
        program_id=program_id,
        page=page
    ).pack()
    add_callback = MenuCallBack(
        level=level + 1,
        action="ctgs",
        program_id=program_id,
        training_day_id=training_day_id,
        page=page
    ).pack()
    edit_callback = MenuCallBack(
        level=level + 1,
        action="edit_excs",
        program_id=program_id,
        training_day_id=training_day_id,
        page=page
    ).pack()
    if action.startswith("shd/"):
        back_callback = MenuCallBack(
            level=1,
            action='t_day',
            training_day_id=training_day_id,
            program_id=program_id,
            page=page
        ).pack()
        add_callback = MenuCallBack(
            level=level + 1,
            action=f"shd/ctgs",
            program_id=program_id,
            training_day_id=training_day_id,
            page=page
        ).pack()
        edit_callback = MenuCallBack(
            level=level + 1,
            action="shd/edit_excs",
            program_id=program_id,
            training_day_id=training_day_id,
            page=page
        ).pack()

    back_button = InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)
    add_button = InlineKeyboardButton(text="➕ Добавить упражнение", callback_data=add_callback)
    edit_button = InlineKeyboardButton(text="✏️ Редактировать упражнения", callback_data=edit_callback)
    if empty_list:
        keyboard.add(back_button, add_button)
    else:
        keyboard.add(back_button, add_button, edit_button)
    return keyboard.adjust(*sizes).as_markup()


def get_category_btns(
        *,
        level: int,
        action: str,
        program_id: int,
        categories: list,
        page: int,
        training_day_id: int,
        user_name: str,
        len_custom: int,
        sizes: tuple[int] = (3, 3),
) -> InlineKeyboardMarkup:
    """
    Возвращает клавиатуру категорий упражнений.
    Каждая категория — кнопка с количеством упражнений.
    """
    keyboard = InlineKeyboardBuilder()
    custom_exercise = MenuCallBack(
        action=f"ctg",
        level=level + 1,
        training_day_id=training_day_id,
        program_id=program_id,
        page=page,
        empty=True,
    ).pack()
    if action.startswith("shd/"):
        custom_exercise = MenuCallBack(
            action=f"shd/ctg",
            level=level + 1,
            training_day_id=training_day_id,
            program_id=program_id,
            page=page,
            empty=True,
        ).pack()
    button = InlineKeyboardButton(text=f"{user_name} ({len_custom})", callback_data=custom_exercise)
    keyboard.add(button)
    for category, count in categories:
        callback = MenuCallBack(
            action=f"ctg",
            level=level + 1,
            category_id=category.id,
            training_day_id=training_day_id,
            program_id=program_id,
            page=page
        ).pack()
        if action.startswith("shd/"):
            callback = MenuCallBack(
                action=f"shd/ctg",
                level=level + 1,
                category_id=category.id,
                training_day_id=training_day_id,
                program_id=program_id,
                page=page
            ).pack()
        button_text = f"{category.name} ({count})"
        button = InlineKeyboardButton(text=button_text, callback_data=callback)
        keyboard.add(button)

    padding = (-len(categories)) % sizes[0] - 1
    if len(categories) >= 3:
        for _ in range(padding):
            keyboard.add(InlineKeyboardButton(text=" ", callback_data=EMPTY_CALLBACK))

    back_callback = MenuCallBack(
        level=level - 1,
        action='edit_trd',
        training_day_id=training_day_id,
        program_id=program_id,
        page=page
    ).pack()
    if action.startswith("shd/"):
        back_callback = MenuCallBack(
            level=level - 1,
            action='shd/edit_trd',
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
        template_exercises: list = None,
        page: int,
        category_id: int = None,
        training_day_id: int,
        action: str,
        empty: bool,
        user_exercises: list,
        sizes: tuple[int] = (2, 2),
) -> InlineKeyboardMarkup:
    """
    Возвращает клавиатуру упражнений по выбранной категории.
    Есть кнопка для добавления своего упражнения и возврата назад.
    """
    keyboard = InlineKeyboardBuilder()
    k = 0
    if not empty:
        if action.startswith("add_"):
            action = action.split("_", 1)[-1]
        if user_exercises:
            for exercise in user_exercises:
                callback = MenuCallBack(
                    action="add_ex_custom",
                    level=level,
                    exercise_id=exercise.id,
                    category_id=exercise.category_id,
                    training_day_id=training_day_id,
                    program_id=program_id,
                    page=page,
                ).pack()
                if action.startswith("shd/"):
                    callback = MenuCallBack(
                        action=f"shd/add_ex_custom",
                        level=level,
                        exercise_id=exercise.id,
                        category_id=exercise.category_id,
                        training_day_id=training_day_id,
                        program_id=program_id,
                        page=page,
                    ).pack()
                button = InlineKeyboardButton(text=f"➕ {exercise.name}", callback_data=callback)
                keyboard.add(button)
                k += 1
        if template_exercises:
            for exercise in template_exercises:
                callback = MenuCallBack(
                    action="add_ex",
                    level=level,
                    exercise_id=exercise.id,
                    category_id=exercise.category_id,
                    training_day_id=training_day_id,
                    program_id=program_id,
                    page=page
                ).pack()
                if action.startswith("shd/"):
                    callback = MenuCallBack(
                        action=f"shd/add_ex",
                        level=level,
                        exercise_id=exercise.id,
                        category_id=exercise.category_id,
                        training_day_id=training_day_id,
                        program_id=program_id,
                        page=page
                    ).pack()
                button = InlineKeyboardButton(text=f"➕ {exercise.name}", callback_data=callback)
                keyboard.add(button)
                k += 1
    else:
        if action.startswith("add_"):
            action = action.split("_", 1)[-1]
        if user_exercises:
            for exercise in user_exercises:
                callback = MenuCallBack(
                    action="add_ex_custom",
                    level=level,
                    exercise_id=exercise.id,
                    category_id=exercise.category_id,
                    training_day_id=training_day_id,
                    program_id=program_id,
                    page=page,
                    empty=True,
                ).pack()
                if action.startswith("shd/"):
                    callback = MenuCallBack(
                        action=f"shd/add_ex_custom",
                        level=level,
                        exercise_id=exercise.id,
                        category_id=exercise.category_id,
                        training_day_id=training_day_id,
                        program_id=program_id,
                        page=page,
                        empty=True,
                    ).pack()
                button = InlineKeyboardButton(text=f"➕ {exercise.name}", callback_data=callback)
                keyboard.add(button)
                k += 1
        if template_exercises:
            for exercise in template_exercises:
                callback = MenuCallBack(
                    action="add_ex",
                    level=level,
                    exercise_id=exercise.id,
                    category_id=exercise.category_id,
                    training_day_id=training_day_id,
                    program_id=program_id,
                    page=page,
                    empty=True,
                ).pack()
                if action.startswith("shd/"):
                    callback = MenuCallBack(
                        action=f"shd/add_ex",
                        level=level,
                        exercise_id=exercise.id,
                        category_id=exercise.category_id,
                        training_day_id=training_day_id,
                        program_id=program_id,
                        page=page,
                        empty=True,
                    ).pack()
                button = InlineKeyboardButton(text=f"➕ {exercise.name}", callback_data=callback)
                keyboard.add(button)
                k += 1

    padding = (-k) % sizes[0]
    if k > 2:
        for _ in range(padding):
            keyboard.add(InlineKeyboardButton(text=" ", callback_data=EMPTY_CALLBACK))
    if k == 1:
        sizes = (1, 2)
    back_callback = MenuCallBack(
        level=level - 1,
        action="ctgs",
        training_day_id=training_day_id,
        program_id=program_id,
        page=page
    ).pack()
    custom_exercises = MenuCallBack(
        level=level + 1,
        action="custom_excs",
        training_day_id=training_day_id,
        category_id=category_id,
        program_id=program_id,
        page=page,
        empty=empty,
    ).pack()
    if action.startswith("shd/"):
        back_callback = MenuCallBack(
            level=level - 1,
            action="shd/ctgs",
            training_day_id=training_day_id,
            program_id=program_id,
            page=page,
        ).pack()
        custom_exercises = MenuCallBack(
            level=level + 1,
            action="shd/custom_excs",
            training_day_id=training_day_id,
            program_id=program_id,
            category_id=category_id,
            page=page,
            empty=empty,
        ).pack()

    custom_exercises_button = InlineKeyboardButton(text="🫵 Ваши упражнения",
                                                   callback_data=custom_exercises)
    back_button = InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)
    keyboard.row(back_button, custom_exercises_button)
    return keyboard.adjust(*sizes).as_markup()


def get_custom_exercise_btns(
        *,
        level: int,
        program_id: int,
        page: int,
        category_id: int,
        training_day_id: int,
        exercise_id: int,
        action: str,
        empty: bool,
        user_exercises: list,
) -> InlineKeyboardMarkup:
    """
    Возвращает клавиатуру для добавления пользовательского упражнения.
    """

    keyboard = InlineKeyboardBuilder()

    if get_action_part(action) == "to_edit":
        for exercise in user_exercises:
            button_text = f"👉 {exercise.name}" if exercise_id == exercise.id else f"🔘 {exercise.name}"
            exercise_button = InlineKeyboardButton(
                text=button_text,
                callback_data=MenuCallBack(
                    action="to_edit",
                    level=level,
                    exercise_id=exercise.id,
                    page=page,
                    training_day_id=training_day_id,
                    category_id=category_id,
                    program_id=program_id,
                    empty=empty,
                ).pack()
            )
            if action.startswith("shd/"):
                exercise_button = InlineKeyboardButton(
                    text=button_text,
                    callback_data=MenuCallBack(
                        action="shd/to_edit",
                        level=level,
                        exercise_id=exercise.id,
                        category_id=category_id,
                        page=page,
                        training_day_id=training_day_id,
                        program_id=program_id,
                        empty=empty,
                    ).pack()
                )
            keyboard.row(exercise_button)

        if exercise_id is not None:

            delete_callback = MenuCallBack(
                action="del_custom",
                level=level if len(user_exercises) != 1 else level - 1,
                exercise_id=exercise_id,
                page=page,
                training_day_id=training_day_id,
                category_id=category_id,
                program_id=program_id,
                empty=empty,
            ).pack()
            if action.startswith("shd/"):
                delete_callback = MenuCallBack(
                    action="shd/del_custom",
                    level=level if len(user_exercises) != 1 else level - 1,
                    exercise_id=exercise_id,
                    page=page,
                    category_id=category_id,
                    training_day_id=training_day_id,
                    program_id=program_id,
                    empty=empty,
                ).pack()
            delete_button = InlineKeyboardButton(text="🗑️ Удалить упражнение", callback_data=delete_callback)
            back_callback = MenuCallBack(
                level=level - 1,
                action="ctg",
                training_day_id=training_day_id,
                category_id=category_id,
                program_id=program_id,
                page=page,
                empty=empty,
            ).pack()
            custom_exercises = MenuCallBack(
                level=level,
                action="add_u_excs",
                training_day_id=training_day_id,
                category_id=category_id,
                program_id=program_id,
                page=page,
                empty=empty,
            ).pack()
            if action.startswith("shd/"):
                back_callback = MenuCallBack(
                    level=level - 1,
                    action="shd/ctg",
                    training_day_id=training_day_id,
                    category_id=category_id,
                    program_id=program_id,
                    page=page,
                    empty=empty,
                ).pack()
                custom_exercises = MenuCallBack(
                    level=level,
                    action="shd/add_u_excs",
                    training_day_id=training_day_id,
                    category_id=category_id,
                    program_id=program_id,
                    page=page,
                    empty=empty,
                ).pack()
            back_button = InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)
            add_button = InlineKeyboardButton(text="➕ Добавить упражнение", callback_data=custom_exercises)
            keyboard.row(delete_button)
            keyboard.row(back_button, add_button)

        else:
            back_callback = MenuCallBack(
                level=level - 1,
                action="ctg",
                training_day_id=training_day_id,
                category_id=category_id,
                program_id=program_id,
                page=page,
                empty=empty,
            ).pack()
            custom_exercises = MenuCallBack(
                level=level,
                action="add_u_excs",
                training_day_id=training_day_id,
                category_id=category_id,
                program_id=program_id,
                page=page,
                empty=empty,
            ).pack()
            if action.startswith("shd/"):
                back_callback = MenuCallBack(
                    level=level - 1,
                    action="shd/ctg",
                    training_day_id=training_day_id,
                    category_id=category_id,
                    program_id=program_id,
                    page=page,
                    empty=empty,
                ).pack()
                custom_exercises = MenuCallBack(
                    level=level,
                    action="shd/add_u_excs",
                    training_day_id=training_day_id,
                    category_id=category_id,
                    program_id=program_id,
                    page=page,
                    empty=empty,
                ).pack()
            back_button = InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)
            add_button = InlineKeyboardButton(text="➕ Добавить упражнение", callback_data=custom_exercises)
            keyboard.row(back_button, add_button)
    else:
        for exercise in user_exercises:
            exercise_button = InlineKeyboardButton(
                text=f"🔘 {exercise.name}",
                callback_data=MenuCallBack(
                    action="to_edit",
                    level=level,
                    exercise_id=exercise.id,
                    category_id=category_id,
                    page=page,
                    training_day_id=training_day_id,
                    program_id=program_id,
                    empty=empty,
                ).pack()
            )
            if action.startswith("shd/"):
                exercise_button = InlineKeyboardButton(
                    text=f"🔘 {exercise.name}",
                    callback_data=MenuCallBack(
                        action="shd/to_edit",
                        level=level,
                        exercise_id=exercise.id,
                        category_id=category_id,
                        page=page,
                        training_day_id=training_day_id,
                        program_id=program_id,
                        empty=empty,
                    ).pack()
                )
            keyboard.row(exercise_button)

        back_callback = MenuCallBack(
            level=level - 1,
            action="ctg",
            training_day_id=training_day_id,
            category_id=category_id,
            program_id=program_id,
            page=page,
            empty=empty,
        ).pack()
        custom_exercises = MenuCallBack(
            level=level,
            action="add_u_excs",
            training_day_id=training_day_id,
            category_id=category_id,
            program_id=program_id,
            page=page,
            empty=empty,
        ).pack()
        if action.startswith("shd/"):
            back_callback = MenuCallBack(
                level=level - 1,
                action="shd/ctg",
                training_day_id=training_day_id,
                category_id=category_id,
                program_id=program_id,
                page=page,
                empty=empty,
            ).pack()
            custom_exercises = MenuCallBack(
                level=level,
                action="shd/add_u_excs",
                training_day_id=training_day_id,
                category_id=category_id,
                program_id=program_id,
                page=page,
                empty=empty,
            ).pack()
        back_button = InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)
        add_button = InlineKeyboardButton(text="➕ Добавить упражнение", callback_data=custom_exercises)
        keyboard.row(back_button, add_button)

    return keyboard.as_markup()


def get_edit_exercise_btns(
        *,
        level: int,
        program_id: int,
        user_exercises: list,
        page: int,
        exercise_id: int | None,
        training_day_id: int,
        action: str,
) -> InlineKeyboardMarkup:
    """
    Возвращает клавиатуру для редактирования уже существующих упражнений.
    При выборе упражнения появляются кнопки удаления, перемещения и настроек.
    Обрабатывает два пути: из расписания и из настроек программы.
    """
    keyboard = InlineKeyboardBuilder()

    if get_action_part(action) == "to_edit":
        for exercise in user_exercises:
            button_text = f"👉 {exercise.name}" if exercise_id == exercise.id else f"🔘 {exercise.name}"
            exercise_button = InlineKeyboardButton(
                text=button_text,
                callback_data=MenuCallBack(
                    action="to_edit",
                    level=level,
                    exercise_id=exercise.id,
                    page=page,
                    training_day_id=training_day_id,
                    program_id=program_id,
                ).pack()
            )
            if action.startswith("shd/"):
                exercise_button = InlineKeyboardButton(
                    text=button_text,
                    callback_data=MenuCallBack(
                        action="shd/to_edit",
                        level=level,
                        exercise_id=exercise.id,
                        page=page,
                        training_day_id=training_day_id,
                        program_id=program_id,
                    ).pack()
                )
            keyboard.row(exercise_button)

        if exercise_id is not None:
            # Определяем путь (origin) на основе action
            if action.startswith("shd/"):
                back_action = "shd/edit_trd"
            else:
                # Путь из расписания
                back_action = "edit_trd"

            delete_callback = MenuCallBack(
                action="del",
                level=level if len(user_exercises) != 1 else level - 1,
                exercise_id=exercise_id,
                page=page,
                training_day_id=training_day_id,
                program_id=program_id,
            ).pack()
            if action.startswith("shd/"):
                delete_callback = MenuCallBack(
                    action="shd/del",
                    level=level if len(user_exercises) != 1 else level - 1,
                    exercise_id=exercise_id,
                    page=page,
                    training_day_id=training_day_id,
                    program_id=program_id,
                ).pack()
            delete_button = InlineKeyboardButton(text="🗑️ Удалить упражнение", callback_data=delete_callback)

            back_callback = MenuCallBack(
                level=level - 1,
                action=back_action,
                training_day_id=training_day_id,
                program_id=program_id,
                page=page
            ).pack()

            mv_up_callback = MenuCallBack(
                action="mv_up",
                level=level,
                exercise_id=exercise_id,
                page=page,
                training_day_id=training_day_id,
                program_id=program_id,
            ).pack()
            if action.startswith("shd/"):
                mv_up_callback = MenuCallBack(
                    action="shd/mv_up",
                    level=level,
                    exercise_id=exercise_id,
                    page=page,
                    training_day_id=training_day_id,
                    program_id=program_id,
                ).pack()
            mvup_button = InlineKeyboardButton(text="⬆️", callback_data=mv_up_callback)

            mv_down_callback = MenuCallBack(
                action="mv_down",
                level=level,
                exercise_id=exercise_id,
                page=page,
                training_day_id=training_day_id,
                program_id=program_id,
            ).pack()
            if action.startswith("shd/"):
                mv_down_callback = MenuCallBack(
                    action="shd/mv_down",
                    level=level,
                    exercise_id=exercise_id,
                    page=page,
                    training_day_id=training_day_id,
                    program_id=program_id,
                ).pack()

            mvdown_button = InlineKeyboardButton(text="⬇️", callback_data=mv_down_callback)
            back_button = InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)

            settings_callback = MenuCallBack(
                action="ex_stg",
                level=level + 1,
                exercise_id=exercise_id,
                page=page,
                training_day_id=training_day_id,
                program_id=program_id,
            ).pack()
            if action.startswith("shd/"):
                settings_callback = MenuCallBack(
                    action="shd/ex_stg",
                    level=level + 1,
                    exercise_id=exercise_id,
                    page=page,
                    training_day_id=training_day_id,
                    program_id=program_id,
                ).pack()

            settings_button = InlineKeyboardButton(text="⚙️ Настройки", callback_data=settings_callback)

            # Добавляем кнопки перемещения и удаления в ряд
            keyboard.row(mvdown_button, mvup_button, delete_button)
            # Добавляем кнопки настроек и назад в другой ряд
            keyboard.row(back_button, settings_button)
        else:
            # Если exercise_id не задан, просто добавляем кнопку "Назад"
            if action.startswith("shd/"):
                back_action = "shd/edit_trd"
            else:
                # Путь из расписания
                back_action = "edit_trd"

            back_callback = MenuCallBack(
                level=level - 1,
                action=back_action,
                training_day_id=training_day_id,
                program_id=program_id,
                page=page
            ).pack()
            back_button = InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)
            keyboard.row(back_button)
    else:
        for exercise in user_exercises:
            exercise_button = InlineKeyboardButton(
                text=f"🔘 {exercise.name}",
                callback_data=MenuCallBack(
                    action="to_edit",
                    level=level,
                    exercise_id=exercise.id,
                    page=page,
                    training_day_id=training_day_id,
                    program_id=program_id,
                ).pack()
            )
            if action.startswith("shd/"):
                exercise_button = InlineKeyboardButton(
                    text=f"🔘 {exercise.name}",
                    callback_data=MenuCallBack(
                        action="shd/to_edit",
                        level=level,
                        exercise_id=exercise.id,
                        page=page,
                        training_day_id=training_day_id,
                        program_id=program_id,
                    ).pack()
                )
            keyboard.row(exercise_button)

        # Определяем путь (origin) на основе action
        if action.startswith("shd/"):
            back_action = "shd/edit_trd"
        else:
            # Путь из расписания
            back_action = "edit_trd"

        back_callback = MenuCallBack(
            level=level - 1,
            action=back_action,
            training_day_id=training_day_id,
            program_id=program_id,
            page=page
        ).pack()
        back_button = InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)
        keyboard.row(back_button)

    return keyboard.as_markup()


def incr_reduce_sets_reps(level: int, page: int, action: str, exercise_id: int, training_day_id: int, program_id: int,
                          amount: int,
                          operation: str, tp: str, set_id: int) -> InlineKeyboardButton:
    """
    Вспомогательная функция, возвращающая кнопку увеличения/уменьшения повторений или подходов.
    """
    if action.startswith("shd/"):
        return InlineKeyboardButton(
            text=f"{operation}{amount}",
            callback_data=MenuCallBack(
                action=f"shd/{operation}_{amount}_{tp}",
                level=level,
                exercise_id=exercise_id,
                page=page,
                set_id=set_id,
                training_day_id=training_day_id,
                program_id=program_id,
            ).pack())

    return InlineKeyboardButton(
        text=f"{operation}{amount}",
        callback_data=MenuCallBack(
            action=f"{operation}_{amount}_{tp}",
            level=level,
            exercise_id=exercise_id,
            page=page,
            set_id=set_id,
            training_day_id=training_day_id,
            program_id=program_id,
        ).pack())


def get_exercise_settings_btns(
        *,
        level: int,
        action: str,
        program_id: int,
        user_exercise: list,
        base_ex_sets: list,
        page: int,
        exercise_id: int | None,
        training_day_id: int,
) -> InlineKeyboardMarkup:
    """
    Возвращает клавиатуру настройки упражнений:
    - Кнопки увеличения/уменьшения подходов и повторений
    - Кнопка возвращения назад
    """
    keyboard = InlineKeyboardBuilder()
    empty_callback = MenuCallBack(level=level, action=action, exercise_id=exercise_id,
                                  page=page,
                                  training_day_id=training_day_id,
                                  program_id=program_id).pack()
    exercise_button = InlineKeyboardButton(
        text=f"🔘 {user_exercise.name}",
        callback_data=empty_callback)
    keyboard.row(exercise_button)

    set_increase_1 = incr_reduce_sets_reps(level, page, action, exercise_id, training_day_id, program_id,
                                           1, "➕", "sets", -1)
    set_reduce_1 = incr_reduce_sets_reps(level, page, action, exercise_id, training_day_id, program_id,
                                         1, "➖", "sets", -1)

    back_callback = MenuCallBack(
        level=level - 1,
        action="to_edit",
        training_day_id=training_day_id,
        program_id=program_id,
        exercise_id=exercise_id,
        page=page
    ).pack()
    if action.startswith("shd/"):
        back_callback = MenuCallBack(
            level=level - 1,
            action="shd/to_edit",
            training_day_id=training_day_id,
            program_id=program_id,
            exercise_id=exercise_id,
            page=page
        ).pack()
    back_button = InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data=back_callback
    )

    for index, exercise_set in enumerate(base_ex_sets, 1):
        reps_button = InlineKeyboardButton(
            text=f"Reps: {exercise_set.reps}",
            callback_data=empty_callback)
        sets_button = InlineKeyboardButton(
            text=f"Подход {index}",
            callback_data=empty_callback)

        rep_increase_1 = incr_reduce_sets_reps(level, page, action, exercise_id, training_day_id, program_id,
                                               1, "➕", "reps", exercise_set.id)
        rep_reduce_1 = incr_reduce_sets_reps(level, page, action, exercise_id, training_day_id, program_id,
                                             1, "➖", "reps", exercise_set.id)
        keyboard.row(sets_button, reps_button, rep_reduce_1, rep_increase_1)

    set_amount = InlineKeyboardButton(
        text=f"Sets: {len(base_ex_sets)}",
        callback_data=empty_callback)
    keyboard.row(back_button, set_amount, set_reduce_1, set_increase_1)
    return keyboard.as_markup()


def get_callback_btns(
        *,
        btns: dict[str, str],
        sizes: tuple[int] = (2,),
) -> InlineKeyboardMarkup:
    """
    Возвращает клавиатуру из произвольного словаря текст->callback_data.
    """
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
) -> InlineKeyboardMarkup:
    """
    Возвращает клавиатуру с кнопками-ссылками.
    """
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
) -> InlineKeyboardMarkup:
    """
    Возвращает клавиатуру с комбинированными кнопками: часть — callback, часть — url.
    """
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
