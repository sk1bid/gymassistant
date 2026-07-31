"""Пинги отдыха всегда со звуком: убираем тихий режим

Revision ID: b2c4d6e8f0a1
Revises: a1b2c3d4e5f6
Create Date: 2026-07-24

Тихий режим оказался вредным по замыслу. `quiet_rest_pings` по умолчанию стоял
включённым, и промежуточные минутные пинги уходили с disable_notification —
то есть ровно то сообщение, ради которого телефон лежит на скамье экраном вниз,
приходило без звука и вибрации. Пользователь узнавал об окончании отдыха, только
заглянув в чат сам.

Что убираем:

* training_program.quiet_rest_pings — настройка тихих пингов;
* rest_timer.quiet — её снимок на время конкретного отдыха;
* rest_timer.warned — «предупреждение за 30 секунд уже отправлено». Расписание
  пингов теперь считается по границам оставшихся минут (_should_ping в
  workers/rest_notifier.py), отдельного предупреждения нет, и запоминать нечего.

downgrade возвращает колонки со старыми значениями по умолчанию. Сами настройки
пользователей при этом не восстанавливаются — их значения теряются здесь.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b2c4d6e8f0a1'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('training_program', 'quiet_rest_pings')
    op.drop_column('rest_timer', 'quiet')
    op.drop_column('rest_timer', 'warned')


def downgrade() -> None:
    op.add_column(
        'rest_timer',
        sa.Column('warned', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'rest_timer',
        sa.Column('quiet', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        'training_program',
        sa.Column('quiet_rest_pings', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
