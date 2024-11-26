import uuid
from typing import List
from sqlalchemy.dialects.postgresql import UUID

from sqlalchemy import String, Float, DateTime, func, Integer, ForeignKey, Text, BigInteger, Index, CheckConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    created: Mapped[DateTime] = mapped_column(DateTime, default=func.now())
    updated: Mapped[DateTime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


class ExerciseCategory(Base):
    __tablename__ = 'exercise_category'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(), unique=True)


class AdminExercises(Base):
    __tablename__ = 'admin_exercises'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(ForeignKey('exercise_category.id'))
    name: Mapped[str] = mapped_column(String(), unique=True)
    image: Mapped[str] = mapped_column(String())
    description: Mapped[str] = mapped_column(Text)

    exercise_category: Mapped['ExerciseCategory'] = relationship(backref='admin_exercises', lazy='select')


class Banner(Base):
    __tablename__ = 'banner'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(30), unique=True)
    image: Mapped[str] = mapped_column(String(150), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)


class User(Base):
    __tablename__ = 'user'
    __table_args__ = (Index('idx_user_user_id', 'user_id'),)

    id: Mapped[int] = mapped_column(Integer(), primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    name: Mapped[str] = mapped_column(String(20), nullable=False)
    weight: Mapped[float] = mapped_column(Float(), nullable=False)
    actual_program_id: Mapped[int] = mapped_column(Integer(), nullable=True)


class TrainingProgram(Base):
    __tablename__ = 'training_program'
    __table_args__ = (Index('idx_training_program_user_id', 'user_id'),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50))
    user_id: Mapped[int] = mapped_column(ForeignKey('user.user_id'), nullable=False)

    user: Mapped['User'] = relationship(backref='training_program', lazy='select')
    training_days: Mapped[List['TrainingDay']] = relationship(
        'TrainingDay',
        back_populates='training_program',
        cascade='all, delete-orphan'
    )


class TrainingDay(Base):
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
    __tablename__ = 'exercise'
    __table_args__ = (
        Index('idx_exercise_training_day_id', 'training_day_id'),
        CheckConstraint('base_reps > 0', name='check_base_reps_positive'),
        CheckConstraint('base_sets > 0', name='check_base_sets_positive')
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text)
    base_sets: Mapped[int] = mapped_column(Integer(), default=3)
    base_reps: Mapped[int] = mapped_column(Integer(), default=10)
    image: Mapped[str] = mapped_column(String(150))
    training_day_id: Mapped[int] = mapped_column(ForeignKey("training_day.id", ondelete='CASCADE'), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    training_day: Mapped['TrainingDay'] = relationship("TrainingDay", back_populates="exercises", lazy='select')
    exercise_sets: Mapped[List['ExerciseSet']] = relationship(
        "ExerciseSet",
        back_populates="exercise",
        cascade='all, delete-orphan',
        lazy='select'
    )

    # Добавлено поле sets
    sets: Mapped[List['Set']] = relationship("Set", back_populates="exercise", lazy='select')


class ExerciseSet(Base):
    __tablename__ = 'exercise_set'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    reps: Mapped[int] = mapped_column(Integer, CheckConstraint('reps > 0'), nullable=False, default=10)
    exercise_id: Mapped[int] = mapped_column(ForeignKey('exercise.id', ondelete='CASCADE'), nullable=False)

    exercise: Mapped['Exercise'] = relationship('Exercise', back_populates='exercise_sets', lazy='select')


class Set(Base):
    __tablename__ = 'set'
    __table_args__ = (Index('idx_set_exercise_id', 'exercise_id'),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey('exercise.id', ondelete='CASCADE'), nullable=False)
    weight: Mapped[float] = mapped_column(Float(), nullable=False)
    repetitions: Mapped[int] = mapped_column(Integer, nullable=False)
    training_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    exercise: Mapped['Exercise'] = relationship(
        'Exercise', back_populates='sets', lazy='select')
