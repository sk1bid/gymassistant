import uuid

_temp_storage = {}


def store_data_temporarily(data):
    """
    Сохраняет 'data' во временном хранилище и возвращает ключ-строку (UUID).
    """
    key = str(uuid.uuid4())
    _temp_storage[key] = data
    return key


def retrieve_data_temporarily(key):
    """
    Возвращает данные из хранилища по ключу.
    Если ключ не найден, вернёт None.
    """
    return _temp_storage.get(key)
