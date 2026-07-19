"""
Рекомендация веса на следующий подход.

Раньше LSTM дёргалась так:

    if next_ex.name.lower() in ["жим штанги лежа", "жим лёжа", "bench press"]:

то есть сравнением названия со списком строк. Переименовал упражнение — ИИ пропал;
для остальных упражнений его не было никогда.

При этом на вход модель получает признаки, в которых нет ничего специфичного для жима:
вес, повторения, объём, дельта веса, дельта повторений. Она обучена на жиме, но
структурно применима к любому упражнению со штангой. Поэтому:

* упражнение опознаём по каталогу (`admin_exercise_id` / `user_exercise_id`),
  а не по строке названия;
* историю берём по личности упражнения — сквозь все программы пользователя
  (см. database/orm_extra.exercise_identity);
* просим прогноз для любого упражнения, у которого накопилось достаточно подходов.
"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from database.orm_extra import orm_get_last_sets_by_identity
from services.neiro_api import get_press_prediction

# Меньше трёх подходов — предсказывать не из чего, модель выдаст шум.
MIN_HISTORY = 3
# Ровно столько шагов ждёт LSTM (SEQ_LEN в press_api/api.py).
SEQ_LEN = 5


async def predict_next_weight(session: AsyncSession, user_id: int, exercise) -> dict | None:
    """
    Прогноз веса на следующий подход или None, если истории мало / сервис недоступен.

    Падение press-api не должно ронять тренировку: ИИ — подсказка, а не обязательный шаг.
    """
    history = await orm_get_last_sets_by_identity(session, user_id, exercise, limit=SEQ_LEN)
    if len(history) < MIN_HISTORY:
        return None

    prediction = await get_press_prediction(history)

    # press-api отвечает 200 даже на ошибку, кладя её в тело — поэтому проверяем поле,
    # а не только статус (внутри neiro_api он и так проверен).
    if not prediction or prediction.get("error") or not prediction.get("next_weight"):
        if prediction and prediction.get("error"):
            logging.warning("press-api вернул ошибку: %s", prediction["error"])
        return None

    logging.info("прогноз для %s (user_id=%s): %s", exercise.name, user_id, prediction)
    return {
        "next_weight": float(prediction["next_weight"]),
        "plates_each_side": prediction.get("plates_each_side") or [],
        "bar_weight": prediction.get("bar_weight"),
    }
