"""
Тесты API Mini App — сквозь весь слой данных, на живой SQLite.

Моков нет: гоняем настоящие orm_-функции бота по настоящей базе. Это единственный
способ поймать баги вроде UUID-подхода, которые на Postgres молчат, а на SQLite падают.

Запуск (из каталога gymassistant/):
    ./miniapp/.venv/bin/pytest tests/ -q
"""
import hashlib
import hmac
import json
import os
import sys
import tempfile
import urllib.parse
from datetime import timedelta
from pathlib import Path

import pytest

# База — временный файл, свой на каждый прогон: тесты не должны видеть чужие данные.
_TMP_DB = Path(tempfile.mkdtemp()) / "test.db"
os.environ["DB_URL"] = f"sqlite+aiosqlite:///{_TMP_DB}"
os.environ["MINIAPP_BOT_TOKEN"] = "123456:TEST-TOKEN"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from database.engine import create_db, session_maker  # noqa: E402
from miniapp.main import app  # noqa: E402
from miniapp.seed import seed_catalog  # noqa: E402

TOKEN = os.environ["MINIAPP_BOT_TOKEN"]
USER_ID = 777_000_111


def sign(user_id: int = USER_ID, name: str = "Тестер") -> str:
    """Подписанный initData — ровно так его формирует Telegram."""
    fields = {
        "auth_date": "2000000000",
        "query_id": "AAF",
        # Реальный Telegram шлёт и signature (Ed25519-подпись для сторонней валидации).
        # Она ВХОДИТ в data_check_string HMAC — проверяем, что сервер её не выбрасывает.
        "signature": "ZmFrZV9zaWduYXR1cmU",
        "user": json.dumps({"id": user_id, "first_name": name}, ensure_ascii=False),
    }
    check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(fields)


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """
    Чистая база на каждый тест.

    Иначе брошенные тренировки и программы одного теста утекают в следующий —
    пользователь-то один и тот же.
    """
    from database.engine import engine
    from database.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await create_db()
    async with session_maker() as session:
        await seed_catalog(session)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Init-Data": sign()},
    ) as http:
        yield http


# ---------------------------------------------------------------- подпись

@pytest.mark.anyio
async def test_forged_init_data_rejected():
    """
    Главная проверка всего проекта: подменённый user.id должен получать 401.

    Берём валидный initData и меняем в нём id на чужой, не трогая hash, — так и
    выглядела бы попытка писать подходы в чужой аккаунт.
    """
    valid = sign(user_id=111)
    forged = valid.replace(urllib.parse.quote("111"), urllib.parse.quote("222"))
    assert forged != valid

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        assert (await http.get("/api/bootstrap", headers={"X-Init-Data": forged})).status_code == 401
        assert (await http.get("/api/bootstrap", headers={"X-Init-Data": ""})).status_code == 401
        assert (await http.get("/api/bootstrap")).status_code == 401
        # Подпись валидна, но выписана другим ботом — тоже мимо.
        assert (await http.get(
            "/api/bootstrap",
            headers={"X-Init-Data": sign() + "x"},
        )).status_code == 401


# ---------------------------------------------------------------- сквозной сценарий

@pytest.mark.anyio
async def test_full_training_flow(client: httpx.AsyncClient):
    """Регистрация → программа → день → упражнения → тренировка → история."""
    boot = (await client.get("/api/bootstrap")).json()
    assert boot["ok"] and boot["user"]["name"] == "Тестер"
    assert boot["has_program"] is False  # новый пользователь, программ нет

    # --- программа заводится сразу с семью днями и сразу активной
    program = (await client.post("/api/programs", json={"name": "Тест"})).json()["program"]
    assert program["active"] is True

    days = (await client.get(f"/api/programs/{program['id']}/days")).json()["days"]
    assert [d["day_of_week"] for d in days][:2] == ["Понедельник", "Вторник"]

    # --- набиваем понедельник: два обычных упражнения и два круговых
    monday = days[0]["id"]
    catalog = (await client.get("/api/catalog")).json()["categories"]
    chest = next(c for c in catalog if c["name"] == "Грудь")
    picks = (await client.get(f"/api/catalog/{chest['id']}")).json()["exercises"][:4]

    for i, item in enumerate(picks):
        resp = await client.post(
            f"/api/days/{monday}/exercises",
            json={"admin_exercise_id": item["id"], "circle_training": i >= 2},
        )
        assert resp.status_code == 200

    exercises = resp.json()["exercises"]
    assert len(exercises) == 4
    assert [e["position"] for e in exercises] == [0, 1, 2, 3]

    # --- по два подхода в обычных, три круга в круговых
    for e in exercises[:2]:
        await client.patch(f"/api/exercises/{e['id']}", json={"sets": 2, "reps": 8})

    # --- план: 2+2 обычных подхода, затем 3 круга × 2 упражнения
    state = (await client.post("/api/training/start", json={"training_day_id": monday})).json()
    assert state["progress"]["total"] == 2 + 2 + 3 * 2
    assert state["current"]["exercise"]["id"] == exercises[0]["id"]
    assert state["current"]["set_number"] == 1
    assert state["current"]["is_circuit"] is False

    session_id = state["session_id"]

    # --- пишем первый подход: должен появиться таймер отдыха и сдвинуться шаг
    state = (await client.post("/api/training/set", json={
        "session_id": session_id,
        "exercise_id": exercises[0]["id"],
        "weight": 60.0,
        "reps": 8,
    })).json()

    assert state["progress"]["done"] == 1
    assert state["current"]["set_number"] == 2                  # тот же снаряд, второй подход
    assert state["current"]["exercise"]["id"] == exercises[0]["id"]
    assert state["rest"]["left"] > 0                            # таймер поставлен сервером
    assert state["rest"]["total"] == 300                        # rest_between_set по умолчанию

    # --- добиваем всё, что осталось по плану
    while not state["finished"]:
        current = state["current"]
        state = (await client.post("/api/training/set", json={
            "session_id": session_id,
            "exercise_id": current["exercise"]["id"],
            "weight": 50.0,
            "reps": 10,
        })).json()

    assert state["finished"] is True
    assert state["progress"]["done"] == state["progress"]["total"] == 10
    assert state["rest"] is None                                 # после последнего подхода отдыха нет

    # --- круговые шли кругами, а не подряд: 3 круга по 2 упражнения вперемешку
    circuit = [p for p in state["plan"] if p["is_circuit"]]
    assert [p["round_number"] for p in circuit] == [1, 1, 2, 2, 3, 3]
    assert circuit[0]["exercise_id"] != circuit[1]["exercise_id"]
    assert circuit[0]["exercise_id"] == circuit[2]["exercise_id"]

    finish = (await client.post("/api/training/finish", json={"session_id": session_id})).json()
    assert finish["sets"] == 10 and finish["exercises"] == 4

    # --- тренировка в истории, рекорд записан
    history = (await client.get("/api/history")).json()["sessions"]
    assert len(history) == 1 and history[0]["sets"] == 10

    detail = (await client.get(f"/api/history/{session_id}")).json()
    assert len(detail["exercises"]) == 4

    records = (await client.get("/api/stats")).json()["records"]
    assert records[0]["max_weight"] == 60.0


@pytest.mark.anyio
async def test_programs_list_counts_filled_days(client: httpx.AsyncClient):
    """
    GET /api/programs падал на боевых данных: filled_days считался через
    sum(... await ...) внутри comprehension — await делает его async-генератором,
    и sum() его не итерирует. Баг проявляется только когда программа есть.
    """
    program = (await client.post("/api/programs", json={"name": "Список"})).json()["program"]
    day = (await client.get(f"/api/programs/{program['id']}/days")).json()["days"][0]["id"]
    chest = next(
        c for c in (await client.get("/api/catalog")).json()["categories"] if c["name"] == "Грудь"
    )
    item = (await client.get(f"/api/catalog/{chest['id']}")).json()["exercises"][0]
    await client.post(f"/api/days/{day}/exercises", json={"admin_exercise_id": item["id"]})

    resp = await client.get("/api/programs")
    assert resp.status_code == 200
    listed = next(p for p in resp.json()["programs"] if p["id"] == program["id"])
    assert listed["filled_days"] == 1


@pytest.mark.anyio
async def test_history_survives_program_change(client: httpx.AsyncClient):
    """
    Баг 5: рекорды и «прошлый раз» жили на Exercise.id, а он свой в каждой программе.
    Сменил программу — история обнулилась. Теперь агрегация идёт по каталогу,
    поэтому то же упражнение в новой программе помнит и рекорд, и прошлый раз.
    """
    chest = next(
        c for c in (await client.get("/api/catalog")).json()["categories"] if c["name"] == "Грудь"
    )
    bench = (await client.get(f"/api/catalog/{chest['id']}")).json()["exercises"][0]

    async def program_with_bench(name: str) -> tuple[int, int]:
        program = (await client.post("/api/programs", json={"name": name})).json()["program"]
        days = (await client.get(f"/api/programs/{program['id']}/days")).json()["days"]
        day_id = days[0]["id"]
        result = await client.post(
            f"/api/days/{day_id}/exercises", json={"admin_exercise_id": bench["id"]},
        )
        await client.patch(f"/api/exercises/{result.json()['exercises'][0]['id']}", json={"sets": 1})
        return day_id, result.json()["exercises"][0]["id"]

    # Первая программа: жмём 100 кг.
    old_day, old_exercise = await program_with_bench("Старая")
    state = (await client.post("/api/training/start", json={"training_day_id": old_day})).json()
    await client.post("/api/training/set", json={
        "session_id": state["session_id"], "exercise_id": old_exercise, "weight": 100.0, "reps": 5,
    })
    await client.post("/api/training/finish", json={"session_id": state["session_id"]})

    # Вторая программа: то же упражнение, но другая строка Exercise с другим id.
    new_day, new_exercise = await program_with_bench("Новая")
    assert new_exercise != old_exercise

    state = (await client.post("/api/training/start", json={"training_day_id": new_day})).json()
    card = state["current"]["exercise"]

    assert card["record"] == 100.0                              # рекорд не потерялся
    assert card["prev"] == [{"weight": 100.0, "reps": 5}]       # и «прошлый раз» тоже


@pytest.mark.anyio
async def test_set_can_be_fixed_and_removed(client: httpx.AsyncClient):
    """Записанный подход правится и удаляется, шаг тренировки пересчитывается."""
    program = (await client.post("/api/programs", json={"name": "Правки"})).json()["program"]
    day = (await client.get(f"/api/programs/{program['id']}/days")).json()["days"][0]["id"]

    chest = next(
        c for c in (await client.get("/api/catalog")).json()["categories"] if c["name"] == "Грудь"
    )
    item = (await client.get(f"/api/catalog/{chest['id']}")).json()["exercises"][0]
    added = (await client.post(
        f"/api/days/{day}/exercises", json={"admin_exercise_id": item["id"]},
    )).json()["exercises"][0]

    state = (await client.post("/api/training/start", json={"training_day_id": day})).json()
    state = (await client.post("/api/training/set", json={
        "session_id": state["session_id"], "exercise_id": added["id"], "weight": 80.0, "reps": 10,
    })).json()

    set_id = state["sets"][0]["id"]
    assert state["progress"]["done"] == 1

    # Промахнулись по степперу — правим.
    state = (await client.patch(f"/api/training/set/{set_id}", json={
        "weight": 82.5, "reps": 9,
    })).json()
    assert state["sets"][0]["weight"] == 82.5
    assert state["current"]["exercise"]["record"] == 82.5

    # Записали лишний подход — удаляем, шаг откатывается назад.
    state = (await client.delete(f"/api/training/set/{set_id}")).json()
    assert state["progress"]["done"] == 0
    assert state["current"]["set_number"] == 1


@pytest.mark.anyio
async def test_cannot_touch_other_users_data(client: httpx.AsyncClient):
    """Чужие объекты не читаются и не правятся — id в URL сам по себе ничего не даёт."""
    program = (await client.post("/api/programs", json={"name": "Моя"})).json()["program"]
    day = (await client.get(f"/api/programs/{program['id']}/days")).json()["days"][0]["id"]

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test",
        headers={"X-Init-Data": sign(user_id=999_000_222, name="Чужой")},
    ) as stranger:
        assert (await stranger.get(f"/api/programs/{program['id']}/days")).status_code == 404
        assert (await stranger.get(f"/api/day/{day}")).status_code == 404
        assert (await stranger.delete(f"/api/programs/{program['id']}")).status_code == 404
        assert (await stranger.post(
            "/api/training/start", json={"training_day_id": day},
        )).status_code == 404


@pytest.mark.anyio
async def test_program_settings_are_editable(client: httpx.AsyncClient):
    """Баг 7: настройки отдыха лежали в БД, но UI к ним не было. Теперь есть API."""
    program = (await client.post("/api/programs", json={"name": "Настройки"})).json()["program"]
    assert program["settings"]["rest_between_set"] == 300
    assert program["settings"]["circular_rounds"] == 3

    updated = (await client.patch(f"/api/programs/{program['id']}", json={
        "rest_between_set": 90,
        "rest_between_exercise": 120,
        "circular_rounds": 4,
    })).json()["program"]

    assert updated["settings"]["rest_between_set"] == 90
    assert updated["settings"]["rest_between_exercise"] == 120
    assert updated["settings"]["circular_rounds"] == 4


@pytest.mark.anyio
async def test_rest_between_exercise_is_actually_used(client: httpx.AsyncClient):
    """
    Баг 8: rest_between_exercise клали в FSM и никогда не читали — между упражнениями
    обычного блока отдыха не было вовсе. Проверяем, что теперь он ставится.
    """
    program = (await client.post("/api/programs", json={"name": "Отдых"})).json()["program"]
    await client.patch(f"/api/programs/{program['id']}", json={
        "rest_between_set": 60, "rest_between_exercise": 180,
    })

    day = (await client.get(f"/api/programs/{program['id']}/days")).json()["days"][0]["id"]
    chest = next(
        c for c in (await client.get("/api/catalog")).json()["categories"] if c["name"] == "Грудь"
    )
    picks = (await client.get(f"/api/catalog/{chest['id']}")).json()["exercises"][:2]

    for item in picks:
        added = (await client.post(
            f"/api/days/{day}/exercises", json={"admin_exercise_id": item["id"]},
        )).json()["exercises"]
    for e in added:
        await client.patch(f"/api/exercises/{e['id']}", json={"sets": 2})

    state = (await client.post("/api/training/start", json={"training_day_id": day})).json()
    session_id = state["session_id"]

    # Первый подход первого упражнения → впереди второй подход того же → отдых между подходами.
    state = (await client.post("/api/training/set", json={
        "session_id": session_id, "exercise_id": added[0]["id"], "weight": 50.0, "reps": 10,
    })).json()
    assert state["rest"]["total"] == 60

    # Второй подход первого упражнения → впереди уже другое упражнение → отдых между упражнениями.
    state = (await client.post("/api/training/set", json={
        "session_id": session_id, "exercise_id": added[0]["id"], "weight": 50.0, "reps": 10,
    })).json()
    assert state["rest"]["total"] == 180
    assert added[1]["name"] in state["rest"]["next_up"]


@pytest.mark.anyio
async def test_training_survives_reopen(client: httpx.AsyncClient):
    """
    Баг 1: состояние тренировки жило в FSM в памяти, и рестарт пода её обрывал.
    Теперь шаг вычисляется из БД — закрыли Mini App, открыли заново, шаг тот же.
    """
    program = (await client.post("/api/programs", json={"name": "Живучесть"})).json()["program"]
    day = (await client.get(f"/api/programs/{program['id']}/days")).json()["days"][0]["id"]
    chest = next(
        c for c in (await client.get("/api/catalog")).json()["categories"] if c["name"] == "Грудь"
    )
    item = (await client.get(f"/api/catalog/{chest['id']}")).json()["exercises"][0]
    added = (await client.post(
        f"/api/days/{day}/exercises", json={"admin_exercise_id": item["id"]},
    )).json()["exercises"][0]

    state = (await client.post("/api/training/start", json={"training_day_id": day})).json()
    await client.post("/api/training/set", json={
        "session_id": state["session_id"], "exercise_id": added["id"], "weight": 70.0, "reps": 10,
    })

    # «Закрыли приложение» — новый запрос, никакого состояния в памяти.
    restored = (await client.get("/api/training/state")).json()
    assert restored["session_id"] == state["session_id"]
    assert restored["progress"]["done"] == 1
    assert restored["current"]["set_number"] == 2

    # Повторный старт того же дня не плодит вторую тренировку.
    again = (await client.post("/api/training/start", json={"training_day_id": day})).json()
    assert again["session_id"] == state["session_id"]


@pytest.mark.anyio
async def test_bootstrap_today_uses_client_timezone(client: httpx.AsyncClient):
    """
    «Сегодня» считается в поясе ПОЛЬЗОВАТЕЛЯ (заголовок X-Timezone), а не сервера.

    Раньше день брался из date.today() по локали процесса — а контейнер в UTC, и
    юзер мог быть в любом поясе. Теперь пояс присылает телефон, и endpoint обязан
    его уважать; мусорный/пустой пояс безопасно откатывается на дефолт.
    """
    from zoneinfo import ZoneInfo

    from miniapp.config import WEEK_DAYS_RU
    from services.clock import DEFAULT_TZ, today_in

    for tz in ("Pacific/Kiritimati", "Etc/GMT+12", "Europe/Moscow"):
        boot = (await client.get("/api/bootstrap", headers={"X-Timezone": tz})).json()
        assert boot["today_name"] == WEEK_DAYS_RU[today_in(ZoneInfo(tz)).weekday()]

    # Невалидный пояс не роняет запрос и даёт дефолт (НСК), а не 500.
    boot = (await client.get("/api/bootstrap", headers={"X-Timezone": "'; DROP TABLE"})).json()
    assert boot["today_name"] == WEEK_DAYS_RU[today_in(DEFAULT_TZ).weekday()]


# ---------------------------------------------------------------- пропуски


async def _day_with(client: httpx.AsyncClient, name: str, count: int = 2, sets: int = 3):
    """Программа с одним заполненным днём: общая заготовка для тестов про пропуски."""
    program = (await client.post("/api/programs", json={"name": name})).json()["program"]
    day = (await client.get(f"/api/programs/{program['id']}/days")).json()["days"][0]["id"]
    chest = next(
        c for c in (await client.get("/api/catalog")).json()["categories"] if c["name"] == "Грудь"
    )
    picks = (await client.get(f"/api/catalog/{chest['id']}")).json()["exercises"][:count]

    for item in picks:
        added = (await client.post(
            f"/api/days/{day}/exercises", json={"admin_exercise_id": item["id"]},
        )).json()["exercises"]

    for e in added:
        await client.patch(f"/api/exercises/{e['id']}", json={"sets": sets})

    return day, added


@pytest.mark.anyio
async def test_skipped_set_advances_the_plan(client: httpx.AsyncClient):
    """
    Не смог подход — план всё равно едет дальше.

    Раньше выхода не было: шаг тренировки это первое расхождение плана и записанных
    подходов, поэтому сдвинуть его мог только записанный подход. Человек либо писал
    вес, которого не поднимал, либо бросал тренировку целиком.
    """
    day, added = await _day_with(client, "Пропуски")

    state = (await client.post("/api/training/start", json={"training_day_id": day})).json()
    session_id = state["session_id"]
    assert state["current"]["set_number"] == 1

    state = (await client.post("/api/training/skip", json={
        "session_id": session_id, "exercise_id": added[0]["id"],
    })).json()

    assert state["current"]["set_number"] == 2                 # шаг сдвинулся
    assert state["current"]["exercise"]["id"] == added[0]["id"]
    assert state["progress"]["done"] == 1                      # пропуск занял место в плане
    assert state["sets"][0]["skipped"] is True


@pytest.mark.anyio
async def test_skipped_sets_stay_out_of_statistics(client: httpx.AsyncClient):
    """
    Пропущенное двигает план, но не идёт ни в объём, ни в рекорды, ни в «прошлый раз».

    Иначе рекорд по упражнению становился бы нулевым, а история показывала бы
    подходы, которых не было.
    """
    day, added = await _day_with(client, "Статистика", count=1, sets=3)
    exercise_id = added[0]["id"]

    state = (await client.post("/api/training/start", json={"training_day_id": day})).json()
    session_id = state["session_id"]

    await client.post("/api/training/set", json={
        "session_id": session_id, "exercise_id": exercise_id, "weight": 80.0, "reps": 5,
    })
    await client.post("/api/training/skip", json={
        "session_id": session_id, "exercise_id": exercise_id, "whole_exercise": True,
    })

    state = (await client.get("/api/training/state")).json()
    assert state["finished"] is True                            # план отработан целиком
    assert state["progress"]["done"] == 3
    assert [s["skipped"] for s in state["sets"]] == [False, True, True]

    # Рекорд — только по поднятому.
    assert state["current"] is None
    finish = (await client.post("/api/training/finish", json={"session_id": session_id})).json()
    assert finish["sets"] == 1                                  # один настоящий подход из трёх
    assert finish["volume"] == 80.0 * 5

    profile = (await client.get("/api/profile")).json()
    assert profile["total"]["sets"] == 1
    assert profile["total"]["volume"] == 80.0 * 5

    records = (await client.get("/api/stats")).json()
    top = next(r for r in records["records"] if r["exercise_id"] == exercise_id)
    assert top["max_weight"] == 80.0                            # а не 0 от пропущенных


@pytest.mark.anyio
async def test_editing_a_skipped_set_makes_it_count(client: httpx.AsyncClient):
    """Исправил пропуск на настоящий результат — он обязан попасть в статистику."""
    day, added = await _day_with(client, "Передумал", count=1, sets=2)

    state = (await client.post("/api/training/start", json={"training_day_id": day})).json()
    state = (await client.post("/api/training/skip", json={
        "session_id": state["session_id"], "exercise_id": added[0]["id"],
    })).json()

    skipped_id = state["sets"][0]["id"]
    state = (await client.patch(f"/api/training/set/{skipped_id}",
                                json={"weight": 60.0, "reps": 8})).json()

    assert state["sets"][0]["skipped"] is False
    assert (await client.get("/api/profile")).json()["total"]["sets"] == 1


@pytest.mark.anyio
async def test_skip_only_applies_to_the_current_step(client: httpx.AsyncClient):
    """
    Пропустить можно только текущее упражнение.

    Подходы обязаны ложиться в порядке плана: на этом стоит и вычисление шага, и
    определение только что закрытого шага при постановке отдыха.
    """
    day, added = await _day_with(client, "Порядок", count=2)

    state = (await client.post("/api/training/start", json={"training_day_id": day})).json()
    resp = await client.post("/api/training/skip", json={
        "session_id": state["session_id"], "exercise_id": added[1]["id"],   # не текущее
    })
    assert resp.status_code == 400


@pytest.mark.anyio
async def test_rest_after_a_skip_matches_the_next_step(client: httpx.AsyncClient):
    """
    После пропуска ставится тот же отдых, что и после выполненного подхода.

    Здесь легко было сломать тихо. Постановка отдыха определяет «только что закрытый
    шаг» как plan[len(done) - 1], то есть по КОЛИЧЕСТВУ записей в плановом порядке.
    Пропуск — такая же запись, поэтому инвариант держится; но стоит начать писать
    пропуски мимо текущего шага, и длительность отдыха поедет молча.
    """
    program = (await client.post("/api/programs", json={"name": "Отдых после пропуска"})).json()["program"]
    await client.patch(f"/api/programs/{program['id']}", json={
        "rest_between_set": 60, "rest_between_exercise": 180,
    })

    day = (await client.get(f"/api/programs/{program['id']}/days")).json()["days"][0]["id"]
    chest = next(
        c for c in (await client.get("/api/catalog")).json()["categories"] if c["name"] == "Грудь"
    )
    for item in (await client.get(f"/api/catalog/{chest['id']}")).json()["exercises"][:2]:
        added = (await client.post(
            f"/api/days/{day}/exercises", json={"admin_exercise_id": item["id"]},
        )).json()["exercises"]
    for e in added:
        await client.patch(f"/api/exercises/{e['id']}", json={"sets": 2})

    state = (await client.post("/api/training/start", json={"training_day_id": day})).json()
    session_id = state["session_id"]

    # Пропустили первый подход → впереди второй подход ТОГО ЖЕ снаряда.
    state = (await client.post("/api/training/skip", json={
        "session_id": session_id, "exercise_id": added[0]["id"],
    })).json()
    assert state["rest"]["total"] == 60

    # Пропустили второй → впереди уже другое упражнение.
    state = (await client.post("/api/training/skip", json={
        "session_id": session_id, "exercise_id": added[0]["id"],
    })).json()
    assert state["rest"]["total"] == 180
    assert added[1]["name"] in state["rest"]["next_up"]


@pytest.mark.anyio
async def test_skipping_a_whole_circuit_exercise_keeps_the_rounds_intact(client: httpx.AsyncClient):
    """
    «Закончить упражнение» в круговом блоке снимает только его круги.

    Круговой блок разворачивается вперемешку — по одному подходу каждого упражнения
    на круг. Списать «все оставшиеся подходы» здесь означает выбросить свои круги
    и не тронуть чужие; остальные упражнения блока должны доработать до конца.
    """
    program = (await client.post("/api/programs", json={"name": "Круг"})).json()["program"]
    await client.patch(f"/api/programs/{program['id']}", json={"circular_rounds": 3})

    day = (await client.get(f"/api/programs/{program['id']}/days")).json()["days"][0]["id"]
    chest = next(
        c for c in (await client.get("/api/catalog")).json()["categories"] if c["name"] == "Грудь"
    )
    for item in (await client.get(f"/api/catalog/{chest['id']}")).json()["exercises"][:2]:
        added = (await client.post(
            f"/api/days/{day}/exercises",
            json={"admin_exercise_id": item["id"], "circle_training": True},
        )).json()["exercises"]

    state = (await client.post("/api/training/start", json={"training_day_id": day})).json()
    assert state["progress"]["total"] == 6                     # 3 круга × 2 упражнения

    state = (await client.post("/api/training/skip", json={
        "session_id": state["session_id"],
        "exercise_id": added[0]["id"],
        "whole_exercise": True,
    })).json()

    # Списаны три круга первого упражнения, второе осталось при своих трёх.
    assert state["progress"]["done"] == 3
    assert state["current"]["exercise"]["id"] == added[1]["id"]
    assert state["finished"] is False


# ---------------------------------------------------------------- пропущенные дни

TZ_NAME = "Asia/Novosibirsk"
TZ_HEADERS = {"X-Timezone": TZ_NAME}


def _weekday_ru(days_back: int) -> str:
    """Название дня недели, каким он был `days_back` суток назад в поясе клиента."""
    from zoneinfo import ZoneInfo

    from miniapp.config import WEEK_DAYS_RU
    from services.clock import today_in

    return WEEK_DAYS_RU[(today_in(ZoneInfo(TZ_NAME)) - timedelta(days=days_back)).weekday()]


async def _program_with_days(client: httpx.AsyncClient, name: str, days_back: list[int]):
    """
    Программа, в которой заполнены дни недели, отстоящие от сегодня на `days_back`.

    Считаем от сегодняшнего дня, а не от «понедельника»: тест обязан вести себя
    одинаково в любой день недели, когда его запустят.
    """
    program = (await client.post("/api/programs", json={"name": name})).json()["program"]
    days = (await client.get(f"/api/programs/{program['id']}/days")).json()["days"]
    by_name = {d["day_of_week"]: d for d in days}

    chest = next(
        c for c in (await client.get("/api/catalog")).json()["categories"] if c["name"] == "Грудь"
    )
    item = (await client.get(f"/api/catalog/{chest['id']}")).json()["exercises"][0]

    filled = {}
    for back in days_back:
        day = by_name[_weekday_ru(back)]
        await client.post(f"/api/days/{day['id']}/exercises", json={"admin_exercise_id": item["id"]})
        filled[back] = day

    return filled


async def _train(client: httpx.AsyncClient, day_id: int, record: bool = True):
    """Отработать день. record=False — открыть тренировку и не записать ни подхода."""
    started = (await client.post("/api/training/start", json={"training_day_id": day_id})).json()
    if record:
        await client.post("/api/training/set", json={
            "session_id": started["session_id"],
            "exercise_id": started["current"]["exercise"]["id"],
            "weight": 40.0, "reps": 10,
        })
    return started["session_id"]


@pytest.mark.anyio
async def test_missed_day_shows_the_most_recent_one(client: httpx.AsyncClient):
    """
    Из нескольких пропущенных показывается САМЫЙ СВЕЖИЙ.

    Список здесь был бы упрёком, а не помощью: задача экрана — предложить ближайшее
    к отработке, а не подвести итог недели.
    """
    filled = await _program_with_days(client, "Свежесть", [1, 3, 5])

    boot = (await client.get("/api/bootstrap", headers=TZ_HEADERS)).json()
    assert boot["missed"]["id"] == filled[1]["id"]
    assert boot["missed"]["days_ago"] == 1

    # Закрыли вчерашний — подтянулся следующий по свежести, а не «все сразу».
    await _train(client, filled[1]["id"])
    boot = (await client.get("/api/bootstrap", headers=TZ_HEADERS)).json()
    assert boot["missed"]["id"] == filled[3]["id"]
    assert boot["missed"]["days_ago"] == 3


@pytest.mark.anyio
async def test_working_off_a_missed_day_on_another_date_closes_it(client: httpx.AsyncClient):
    """
    Пропустил в понедельник, сделал во вторник — в среду не предлагается.

    Ключ в том, что день закрывается по `training_day_id` сессии, а не по календарной
    дате: отработать понедельник во вторник — это перенос, а не ещё один пропуск.
    Сравнение по датам показывало бы понедельник вечно, пока не наступит следующий.
    """
    filled = await _program_with_days(client, "Перенос", [2])          # позавчера
    target = filled[2]

    boot = (await client.get("/api/bootstrap", headers=TZ_HEADERS)).json()
    assert boot["missed"]["id"] == target["id"]
    assert boot["missed"]["days_ago"] == 2

    # Отрабатываем СЕГОДНЯ — датой сессии будет сегодняшнее число, а не позавчерашнее.
    await _train(client, target["id"])

    boot = (await client.get("/api/bootstrap", headers=TZ_HEADERS)).json()
    assert boot["missed"] is None


@pytest.mark.anyio
async def test_todays_own_workout_is_never_offered_as_missed(client: httpx.AsyncClient):
    """
    Сегодняшняя тренировка не показывается как пропущенная неделю назад.

    Поиск идёт на шесть дней назад, а не на семь, ровно поэтому: седьмой день — это
    тот же день недели, что сегодня. Иначе главный экран показывал бы один день
    дважды («сегодня: Понедельник» и «пропущено: Понедельник, 7 дней назад»), причём
    обе кнопки открывали бы одну и ту же тренировку.
    """
    filled = await _program_with_days(client, "Сегодня", [0])          # только сегодняшний день

    boot = (await client.get("/api/bootstrap", headers=TZ_HEADERS)).json()
    assert boot["today"] is not None
    assert boot["today"]["id"] == filled[0]["id"]
    assert boot["missed"] is None


@pytest.mark.anyio
async def test_training_older_than_a_week_no_longer_closes_the_day(client: httpx.AsyncClient):
    """
    Свежесть — неделя: тренировка недельной давности день уже не закрывает.

    Без окна одна старая тренировка гасила бы напоминание о своём дне недели навсегда.
    """
    from sqlalchemy import update

    from database.models import TrainingSession

    filled = await _program_with_days(client, "Давность", [1])
    target = filled[1]

    session_id = await _train(client, target["id"])
    assert (await client.get("/api/bootstrap", headers=TZ_HEADERS)).json()["missed"] is None

    # Отодвигаем ту же тренировку на восемь суток назад.
    import uuid

    from services.clock import utcnow

    async with session_maker() as db:
        await db.execute(
            update(TrainingSession)
            .where(TrainingSession.id == uuid.UUID(session_id))
            .values(date=utcnow() - timedelta(days=8))
        )
        await db.commit()

    boot = (await client.get("/api/bootstrap", headers=TZ_HEADERS)).json()
    assert boot["missed"]["id"] == target["id"]


@pytest.mark.anyio
async def test_opening_a_workout_without_recording_does_not_close_the_day(client: httpx.AsyncClient):
    """
    Открыть тренировку и ничего не записать — не значит отработать день.

    Иначе случайное нажатие «Начать» гасило бы напоминание, а сама пустая сессия
    всё равно будет убрана уборщиком (`orm_delete_empty_sessions`).
    """
    filled = await _program_with_days(client, "Передумал", [1])
    target = filled[1]

    await _train(client, target["id"], record=False)

    boot = (await client.get("/api/bootstrap", headers=TZ_HEADERS)).json()
    assert boot["missed"]["id"] == target["id"]


@pytest.mark.anyio
async def test_rest_days_are_never_missed(client: httpx.AsyncClient):
    """День без упражнений — это день отдыха, пропустить его нельзя."""
    await _program_with_days(client, "Отдых", [])          # ни одного заполненного дня

    boot = (await client.get("/api/bootstrap", headers=TZ_HEADERS)).json()
    assert boot["missed"] is None


@pytest.mark.anyio
async def test_circuit_step_reports_position_inside_the_round(client: httpx.AsyncClient):
    """
    В круговом блоке видно не только номер круга, но и место внутри него.

    «Круг 1 из 3» отвечает лишь на половину вопроса: сколько раз пройти блок. Стоя
    между тремя станциями, хочется знать, сколько снарядов осталось до конца круга, —
    и раньше эти данные на экран не приезжали вовсе.
    """
    program = (await client.post("/api/programs", json={"name": "Позиция"})).json()["program"]
    await client.patch(f"/api/programs/{program['id']}", json={"circular_rounds": 3})

    day = (await client.get(f"/api/programs/{program['id']}/days")).json()["days"][0]["id"]
    chest = next(
        c for c in (await client.get("/api/catalog")).json()["categories"] if c["name"] == "Грудь"
    )
    for item in (await client.get(f"/api/catalog/{chest['id']}")).json()["exercises"][:3]:
        added = (await client.post(
            f"/api/days/{day}/exercises",
            json={"admin_exercise_id": item["id"], "circle_training": True},
        )).json()["exercises"]

    state = (await client.post("/api/training/start", json={"training_day_id": day})).json()
    session_id = state["session_id"]

    # Круг идёт по упражнениям: 1→2→3, и только потом начинается следующий круг.
    for expected_round, expected_position in [(1, 1), (1, 2), (1, 3), (2, 1)]:
        assert state["current"]["round_number"] == expected_round
        assert state["current"]["exercise_number"] == expected_position
        assert state["current"]["total_exercises"] == 3

        state = (await client.post("/api/training/set", json={
            "session_id": session_id,
            "exercise_id": state["current"]["exercise"]["id"],
            "weight": 30.0, "reps": 10,
        })).json()


@pytest.mark.anyio
async def test_plain_block_reports_position_among_its_exercises(client: httpx.AsyncClient):
    """
    Обычный блок тоже сообщает своё место — на экране оно не показывается, но
    поле обязано быть осмысленным, а не нулевым: экран решает сам, что рисовать.
    """
    day, added = await _day_with(client, "Обычный блок", count=2, sets=2)

    state = (await client.post("/api/training/start", json={"training_day_id": day})).json()
    assert state["current"]["exercise_number"] == 1
    assert state["current"]["total_exercises"] == 2

    for _ in range(2):                                   # закрываем оба подхода первого
        state = (await client.post("/api/training/set", json={
            "session_id": state["session_id"],
            "exercise_id": state["current"]["exercise"]["id"],
            "weight": 50.0, "reps": 10,
        })).json()

    assert state["current"]["exercise_number"] == 2
    assert state["current"]["is_circuit"] is False


# ---------------------------------------------------------------- недельная сводка


async def _backdate(session_id: str, days: int):
    """Отодвигает тренировку на `days` суток назад — для проверок по неделям."""
    import uuid

    from sqlalchemy import update

    from database.models import TrainingSession
    from services.clock import utcnow

    async with session_maker() as db:
        await db.execute(
            update(TrainingSession)
            .where(TrainingSession.id == uuid.UUID(session_id))
            .values(date=utcnow() - timedelta(days=days))
        )
        await db.commit()


@pytest.mark.anyio
async def test_weekly_progress_reports_goal_and_done(client: httpx.AsyncClient):
    """
    Кольцо недели: цель — число тренировочных дней в программе, «сделано» — сколько
    РАЗНЫХ дней этой недели были тренировочными.
    """
    filled = await _program_with_days(client, "Неделя", [0, 2, 4])

    boot = (await client.get("/api/bootstrap", headers=TZ_HEADERS)).json()
    assert boot["week"] == {"done": 0, "goal": 3, "streak": 0}

    await _train(client, filled[0]["id"])
    boot = (await client.get("/api/bootstrap", headers=TZ_HEADERS)).json()
    assert boot["week"]["done"] == 1
    assert boot["week"]["streak"] == 1          # эта неделя уже засчитана в серию


@pytest.mark.anyio
async def test_weekly_streak_counts_consecutive_weeks(client: httpx.AsyncClient):
    """Серия — недели подряд, где была хотя бы одна тренировка."""
    filled = await _program_with_days(client, "Серия", [0, 1])

    await _train(client, filled[0]["id"])                # тренировка этой недели
    prev = await _train(client, filled[1]["id"])         # ещё одна, сегодня же
    await _backdate(prev, days=7)                         # отодвигаем её в прошлую неделю

    boot = (await client.get("/api/bootstrap", headers=TZ_HEADERS)).json()
    assert boot["week"]["done"] == 1                      # на этой неделе — одна
    assert boot["week"]["streak"] == 2                    # эта + прошлая


@pytest.mark.anyio
async def test_weekly_streak_has_grace_but_resets_on_a_full_gap(client: httpx.AsyncClient):
    """
    Серия мягкая: пустая ТЕКУЩАЯ неделя её не рвёт (грейс на неё), но целая пропущенная
    неделя между тренировкой и сегодня — рвёт. Пропуск дня в зале бывает по делу,
    наказывать за него сбросом цепочки демотивирует.
    """
    filled = await _program_with_days(client, "Грейс", [0])
    session_id = await _train(client, filled[0]["id"])

    # Единственную тренировку двигаем в прошлую неделю: этой недели нет, серия держится.
    await _backdate(session_id, days=7)
    boot = (await client.get("/api/bootstrap", headers=TZ_HEADERS)).json()
    assert boot["week"]["done"] == 0
    assert boot["week"]["streak"] == 1

    # Двигаем на позапрошлую: между ней и сегодня целая пустая неделя — грейса не хватает.
    await _backdate(session_id, days=14)
    boot = (await client.get("/api/bootstrap", headers=TZ_HEADERS)).json()
    assert boot["week"]["streak"] == 0
