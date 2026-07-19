import uuid
from typing import List

from sqlalchemy import (
    String, Float, DateTime, func, Integer, ForeignKey, Text,
    BigInteger, Index, CheckConstraint, Boolean
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship
)

class Base(DeclarativeBase):
    """
    Базовый класс с полями created/updated для всех таблиц.
    """
    created: Mapped[DateTime] = mapped_column(DateTime, default=func.now())
    updated: Mapped[DateTime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

class ExerciseCategory(Base):
    """
    Класс категорий для упражнений
    """
    __tablename__ = 'exercise_category'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(), unique=True)


class AdminExercises(Base):
    """
    Класс предустановленных упражнений
    """
    __tablename__ = 'admin_exercises'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(ForeignKey('exercise_category.id'))
    name: Mapped[str] = mapped_column(String(), unique=True)
    description: Mapped[str] = mapped_column(Text)

    exercise_category: Mapped['ExerciseCategory'] = relationship(backref='admin_exercises', lazy='select')

    exercises_admin: Mapped[List['Exercise']] = relationship(
        'Exercise',
        back_populates='admin_exercise',
        cascade='all, delete-orphan',
        lazy='select',
        passive_deletes=True
    )


class UserExercises(Base):
    """
    Класс пользовательских упражнений
    """
    __tablename__ = 'user_exercises'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(ForeignKey('exercise_category.id'))
    user_id: Mapped[int] = mapped_column(ForeignKey('user.user_id'))
    name: Mapped[str] = mapped_column(String())
    description: Mapped[str] = mapped_column(Text)
    circle_training: Mapped[bool] = mapped_column(Boolean(), default=False)

    exercise_category: Mapped['ExerciseCategory'] = relationship(backref='user_exercises', lazy='select')
    user: Mapped['User'] = relationship(backref='user_exercises', lazy='select')

    exercises_user: Mapped[List['Exercise']] = relationship(
        'Exercise',
        back_populates='user_exercise',
        cascade='all, delete-orphan',
        lazy='select',
        passive_deletes=True
    )


class Banner(Base):
    """
    Класс для изображений в боте
    """
    __tablename__ = 'banner'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(30), unique=True)
    image: Mapped[str] = mapped_column(String(150), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)


class User(Base):
    """
    Класс для пользователя
    """
    __tablename__ = 'user'
    __table_args__ = (Index('idx_user_user_id', 'user_id'),)

    id: Mapped[int] = mapped_column(Integer(), primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    name: Mapped[str] = mapped_column(String(20), nullable=False)
    weight: Mapped[float] = mapped_column(Float(), nullable=False)
    actual_program_id: Mapped[int] = mapped_column(Integer(), nullable=True)

    # Связь с TrainingSession (см. модель ниже), чтобы быстро получить все сессии пользователя
    training_sessions: Mapped[List['TrainingSession']] = relationship(
        "TrainingSession",
        back_populates="user",
        lazy='select',
        cascade='all, delete-orphan'
    )


class TrainingProgram(Base):
    """
    Класс для программ тренировок
    """
    __tablename__ = 'training_program'
    __table_args__ = (Index('idx_training_program_user_id', 'user_id'),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50))
    user_id: Mapped[int] = mapped_column(ForeignKey('user.user_id'), nullable=False)
    rest_between_exercise: Mapped[int] = mapped_column(Integer(), nullable=False, default=300)  # 5 минут стандарт
    rest_between_set: Mapped[int] = mapped_column(Integer(), nullable=False, default=300)
    circular_rounds: Mapped[int] = mapped_column(Integer(), nullable=False, default=3)  # 3 круга стандарт
    circular_rest_between_rounds: Mapped[int] = mapped_column(Integer(), nullable=False,
                                                              default=300)  # 5 минут стандарт
    circular_rest_between_exercise: Mapped[int] = mapped_column(Integer(), nullable=False,
                                                                default=60)  # 1 минут стандарт
    # Тихие промежуточные пинги отдыха: минутные напоминания приходят без звука,
    # звонко пингуем только за 30 секунд до конца и в момент окончания.
    quiet_rest_pings: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)

    user: Mapped['User'] = relationship(backref='training_program', lazy='select')
    training_days: Mapped[List['TrainingDay']] = relationship(
        'TrainingDay',
        back_populates='training_program',
        cascade='all, delete-orphan'
    )


class TrainingDay(Base):
    """
    Класс для дня недели
    """
    __tablename__ = 'training_day'
    __table_args__ = (Index('idx_training_day_program_id', 'training_program_id'),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    day_of_week: Mapped[str] = mapped_column(String(20), nullable=False)
    training_program_id: Mapped[int] = mapped_column(ForeignKey('training_program.id', ondelete='CASCADE'),
                                                     nullable=False)

    training_program: Mapped['TrainingProgram'] = relationship(
        'TrainingProgram',
        back_populates='training_days',
        lazy='select'
    )
    exercises: Mapped[List['Exercise']] = relationship(
        'Exercise',
        back_populates='training_day',
        cascade='all, delete-orphan'
    )


class Exercise(Base):
    """
    Класс для упражнения
    """
    __tablename__ = 'exercise'
    __table_args__ = (
        Index('idx_exercise_training_day_id', 'training_day_id'),
        CheckConstraint('base_reps > 0', name='check_base_reps_positive'),
        CheckConstraint('base_sets > 0', name='check_base_sets_positive'),
        CheckConstraint(
            """
            (admin_exercise_id IS NOT NULL AND user_exercise_id IS NULL)
            OR
            (admin_exercise_id IS NULL AND user_exercise_id IS NOT NULL)
            """,
            name='check_admin_or_user_exercise'
        )
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text)
    base_sets: Mapped[int] = mapped_column(Integer(), default=3)
    base_reps: Mapped[int] = mapped_column(Integer(), default=10)
    training_day_id: Mapped[int] = mapped_column(ForeignKey("training_day.id", ondelete='CASCADE'), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    circle_training: Mapped[bool] = mapped_column(Boolean(), default=False)

    admin_exercise_id: Mapped[int] = mapped_column(ForeignKey('admin_exercises.id', ondelete='CASCADE'), nullable=True)
    user_exercise_id: Mapped[int] = mapped_column(ForeignKey('user_exercises.id', ondelete='CASCADE'), nullable=True)

    training_day: Mapped['TrainingDay'] = relationship("TrainingDay", back_populates="exercises", lazy='select')
    exercise_sets: Mapped[List['ExerciseSet']] = relationship(
        "ExerciseSet",
        back_populates="exercise",
        cascade='all, delete-orphan',
        lazy='select'
    )
    sets: Mapped[List['Set']] = relationship("Set", back_populates="exercise", lazy='select')

    admin_exercise: Mapped['AdminExercises'] = relationship(
        "AdminExercises",
        back_populates="exercises_admin",
        lazy='select',
        passive_deletes=True
    )

    user_exercise: Mapped['UserExercises'] = relationship(
        "UserExercises",
        back_populates="exercises_user",
        lazy='select',
        passive_deletes=True
    )


class ExerciseSet(Base):
    """
    Класс, содержащий целевое кол-во повторений, заданное пользователем
    """
    __tablename__ = 'exercise_set'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    reps: Mapped[int] = mapped_column(Integer, CheckConstraint('reps > 0'), nullable=False, default=10)
    exercise_id: Mapped[int] = mapped_column(ForeignKey('exercise.id', ondelete='CASCADE'), nullable=False)

    exercise: Mapped['Exercise'] = relationship('Exercise', back_populates='exercise_sets', lazy='select')


class TrainingSession(Base):
    """
    Класс тренировки пользователя
    """
    __tablename__ = 'training_session'

    # Используем UUID в качестве первичного ключа
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(ForeignKey('user.user_id', ondelete='CASCADE'), nullable=False)
    date: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    note: Mapped[str] = mapped_column(Text, nullable=True)
    # Пока NULL — тренировка идёт. Это и есть источник правды о «тренировка в процессе»:
    # раньше им был FSM в памяти, и рестарт пода обрывал тренировку.
    finished_at: Mapped[DateTime] = mapped_column(DateTime, nullable=True)
    # Из какого дня недели запущена — чтобы восстановить экран тренировки после закрытия Mini App.
    training_day_id: Mapped[int] = mapped_column(
        ForeignKey('training_day.id', ondelete='SET NULL'), nullable=True
    )

    user: Mapped['User'] = relationship(
        "User",
        back_populates="training_sessions",
        lazy='select'
    )

    sets: Mapped[List['Set']] = relationship(
        "Set",
        back_populates="training_session",
        cascade='all, delete-orphan',
        lazy='select'
    )


class RestTimer(Base):
    """
    Серверный таймер отдыха.

    Живёт в БД, а не в памяти процесса: пользователь закрывает Mini App (и его
    JS-таймер умирает), под бота может перезапуститься — таймер обязан пережить
    и то, и другое. Ставить таймер могут оба клиента: и бот, и Mini App через API,
    это просто строка в таблице. Пингует воркер в процессе бота.
    """
    __tablename__ = 'rest_timer'
    __table_args__ = (Index('idx_rest_timer_active', 'active'),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    ends_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    total_seconds: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    # Когда воркер последний раз слал сообщение (нужно, чтобы пинговать раз в минуту,
    # а не на каждой итерации цикла).
    last_ping: Mapped[DateTime] = mapped_column(DateTime, nullable=True)
    # Что удалить перед отправкой следующего пинга. Именно удалить и прислать новое:
    # редактирование сообщения в Telegram не даёт ни пуша, ни вибрации.
    message_id: Mapped[int] = mapped_column(Integer(), nullable=True)
    # Звонкий пинг за 30 секунд до конца шлём один раз — здесь отмечаем, что уже слали.
    warned: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    quiet: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)

    # Что будет после отдыха — показываем в тексте пинга («Дальше: Жим лёжа, подход 2»).
    next_up: Mapped[str] = mapped_column(String(150), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)


class Set(Base):
    """
    Класс выполненных пользователем подходов
    """
    __tablename__ = 'set'
    __table_args__ = (Index('idx_set_exercise_id', 'exercise_id'),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey('exercise.id', ondelete='CASCADE'),
        nullable=False
    )
    weight: Mapped[float] = mapped_column(Float(), nullable=False)
    repetitions: Mapped[int] = mapped_column(Integer, nullable=False)

    training_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('training_session.id', ondelete='CASCADE'),
        nullable=False
    )

    exercise: Mapped['Exercise'] = relationship(
        'Exercise',
        back_populates='sets',
        lazy='select'
    )
    training_session: Mapped['TrainingSession'] = relationship(
        "TrainingSession",
        back_populates="sets",
        lazy='select'
    )
