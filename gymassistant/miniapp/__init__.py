"""
Mini App: веб-интерфейс GYM.assistant.

Пакет запускается из корня проекта (`uvicorn miniapp.main:app`), поэтому `database`,
`services` и прочие пакеты бота импортируются как обычно — без правки sys.path.

Слои:
    config / auth / db / deps / ownership   — инфраструктура запроса
    schemas / serializers                   — что приходит и что уходит
    state                                   — сборка состояния тренировки
    routers/                                — HTTP, по одному модулю на раздел
    main                                    — сборка приложения

Бизнес-логика хранения живёт в database/orm_query.py бота и здесь не дублируется.
"""
