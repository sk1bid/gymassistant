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
from pathlib import Path

import pytest

# База — временный файл, свой на каждый прогон: тесты не должны видеть чужие данные.
_TMP_DB = Path(tempfile.mkdtemp()) / "test.db"
os.environ["DB_URL"] = f"sqlite+aiosqlite:///{_TMP_DB}"
os.environ["MINIAPP_BOT_TOKEN"] = "123456:TEST-TOKEN"
os.environ.setdefault("NEIRO_API_URL", "http://127.0.0.1:9/predict")  # заведомо мёртвый

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
        "quiet_rest_pings": False,
    })).json()["program"]

    assert updated["settings"]["rest_between_set"] == 90
    assert updated["settings"]["circular_rounds"] == 4
    assert updated["settings"]["quiet_rest_pings"] is False


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
