"""Пропущенный подход — тоже факт тренировки

Revision ID: c3d5e7f9a1b2
Revises: b2c4d6e8f0a1
Create Date: 2026-07-24

Раньше уйти с упражнения, которое не пошло, было нельзя вовсе. Шаг тренировки
вычисляется как первое расхождение между планом и записанными подходами
(services/workout.py), поэтому план двигался ТОЛЬКО фактом записанного подхода:
не смог третий — либо записывай его, соврав про вес, либо бросай тренировку.
Промежуточного не было.

`set.skipped` закрывает это, ничего не ломая в самой конструкции: пропущенный
подход — обычная строка, которая двигает план наравне с выполненным, но в объём,
рекорды, графики и «прошлый раз» не попадает. Вес и повторения у неё нулевые.

server_default=false, поэтому все уже записанные подходы остаются выполненными.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c3d5e7f9a1b2'
down_revision: Union[str, None] = 'b2c4d6e8f0a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'set',
        sa.Column('skipped', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    # Пропущенные подходы после отката превратятся в выполненные с нулевым весом —
    # поэтому сначала убираем их, а уже потом колонку.
    op.execute("DELETE FROM \"set\" WHERE skipped")
    op.drop_column('set', 'skipped')
