"""
Точка входа Mini App.

    uvicorn miniapp.main:app --port 8099    (из каталога gymassistant/)

Снаружи живёт за nginx на https://sk1bid.ru/gym/. Наружу сам не ходит никуда,
кроме press-api внутри кластера, поэтому SOCKS5-прокси, без которого не может
работать бот, ему не нужен: страницу телефон грузит с sk1bid.ru напрямую,
а подпись initData проверяется локально.
"""
import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from database.engine import create_db, session_maker
from miniapp.config import STATIC_DIR
from miniapp.routers import all_routers
from miniapp.seed import seed_catalog

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="GYM.assistant Mini App", docs_url=None, redoc_url=None)


class NoCacheStatic(StaticFiles):
    """
    Отдаёт статику с Cache-Control: no-cache.

    SPA без сборщика: js/css/html меняются на месте, а имена файлов стабильны (нет
    content-hash в имени). Без Cache-Control мобильный webview Telegram кэширует
    эвристически и не ревалидирует — на телефоне остаётся старый main.js, хотя на
    десктопе свежий уже подтянулся. no-cache не запрещает кэш, а обязывает проверять
    по ETag: не изменилось — 304, изменилось — новый файл. Именно то, что нужно
    приложению, которое обновляется подменой файлов, а не пересборкой с новыми именами.
    """

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response

for router in all_routers:
    app.include_router(router)


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.on_event("startup")
async def on_startup():
    await create_db()  # функция бота, без изменений: создаёт таблицы и категории
    async with session_maker() as session:
        await seed_catalog(session)
    logging.info("Mini App готов")


# Монтируется последним: забирает всё, что не разобрали роуты выше.
app.mount("/", NoCacheStatic(directory=STATIC_DIR, html=True), name="static")
