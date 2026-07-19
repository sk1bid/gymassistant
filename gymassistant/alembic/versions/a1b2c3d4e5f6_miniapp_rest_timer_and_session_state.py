"""Mini App: таймер отдыха в БД, состояние тренировки, тихие пинги

Revision ID: a1b2c3d4e5f6
Revises: f79c16648e14
Create Date: 2026-07-14

Что добавляет:

* rest_timer — серверный таймер отдыха. Раньше отдых крутился в asyncio-таске с
  состоянием в FSM (MemoryStorage), и рестарт пода тихо убивал его на середине.
* training_session.finished_at — признак «тренировка идёт». Тоже жил в памяти.
* training_session.training_day_id — из какого дня запущена тренировка; без этого
  нельзя восстановить экран после закрытия Mini App.
* training_program.quiet_rest_pings — минутные напоминания без звука.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f79c16648e14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'training_program',
        sa.Column('quiet_rest_pings', sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.add_column('training_session', sa.Column('finished_at', sa.DateTime(), nullable=True))
    op.add_column('training_session', sa.Column('training_day_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_training_session_training_day',
        'training_session', 'training_day',
        ['training_day_id'], ['id'],
        ondelete='SET NULL',
    )

    # Все существующие тренировки — завершённые. Иначе они выглядели бы как идущие
    # прямо сейчас, и приложение попыталось бы «продолжить» тренировку двухлетней давности.
    op.execute("UPDATE training_session SET finished_at = date WHERE finished_at IS NULL")

    op.create_table(
        'rest_timer',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('chat_id', sa.BigInteger(), nullable=False),
        sa.Column('ends_at', sa.DateTime(), nullable=False),
        sa.Column('total_seconds', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_ping', sa.DateTime(), nullable=True),
        sa.Column('message_id', sa.Integer(), nullable=True),
        sa.Column('warned', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('quiet', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('next_up', sa.String(length=150), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created', sa.DateTime(), nullable=True),
        sa.Column('updated', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        # Таймер у пользователя ровно один: новый отдых перезаписывает старый.
        sa.UniqueConstraint('user_id'),
    )
    op.create_index('idx_rest_timer_active', 'rest_timer', ['active'])


def downgrade() -> None:
    op.drop_index('idx_rest_timer_active', table_name='rest_timer')
    op.drop_table('rest_timer')

    op.drop_constraint('fk_training_session_training_day', 'training_session', type_='foreignkey')
    op.drop_column('training_session', 'training_day_id')
    op.drop_column('training_session', 'finished_at')

    op.drop_column('training_program', 'quiet_rest_pings')
