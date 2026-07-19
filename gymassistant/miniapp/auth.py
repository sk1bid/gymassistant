"""
Единственное место во всём Mini App, которое знает про Telegram.

Подпись initData проверяется локально: HMAC-SHA256, ключ выводится из токена бота
строкой "WebAppData". Обращений к api.telegram.org нет — поэтому блокировка
телеграмовских подсетей провайдером Mini App не касается: страницу телефон грузит
напрямую с sk1bid.ru, а подпись мы считаем сами.

Всё, что мешает постороннему писать подходы в чужой аккаунт, — эти тридцать строк.
"""
import hashlib
import hmac
import json
import time
from typing import Annotated
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException

from miniapp.config import BOT_TOKEN, MAX_AUTH_AGE

# Ключ HMAC зависит только от токена — считаем один раз при импорте.
_SECRET = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()


def verify_init_data(init_data: str) -> dict:
    """
    Проверяет подпись и возвращает Telegram-пользователя.

    Хэш считается по всем полям, кроме самого hash, поэтому любая правка данных —
    и подмена user.id в первую очередь — его ломает.
    """
    if not init_data:
        raise HTTPException(401, "нет initData")

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received = pairs.pop("hash", None)
    if not received:
        raise HTTPException(401, "в initData нет hash")

    # Исключаем только hash. Поле signature (отдельная Ed25519-подпись Telegram для
    # сторонней валидации) в HMAC-строку ВХОДИТ наравне с остальными: Telegram считает
    # data_check_string по всем полям, кроме hash. Выбросишь signature — хэш не сойдётся.
    check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    expected = hmac.new(_SECRET, check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, received):
        raise HTTPException(401, "подпись initData неверна")

    try:
        auth_date = int(pairs.get("auth_date", 0))
    except ValueError:
        raise HTTPException(401, "битый auth_date")

    if time.time() - auth_date > MAX_AUTH_AGE:
        raise HTTPException(401, "initData просрочен")

    user = json.loads(pairs.get("user", "{}"))
    if not user.get("id"):
        raise HTTPException(401, "в initData нет пользователя")

    return user


async def telegram_user(x_init_data: Annotated[str | None, Header()] = None) -> dict:
    """
    Подписанный Telegram-пользователь текущего запроса.

    initData едет в заголовке X-Init-Data, а не в теле, — так GET-эндпоинты остаются
    нормальными GET-ами, и ни один роут не может случайно забыть про проверку подписи:
    без этой зависимости он просто не узнает, кто пришёл.
    """
    return verify_init_data(x_init_data or "")


TgUser = Annotated[dict, Depends(telegram_user)]
