"""add broadcasts

Revision ID: a1b2c3d4e5f6
Revises: e71938e50ad2
Create Date: 2026-06-26 14:30:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'e71938e50ad2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ─── broadcast_campaigns ─────────────────────────────
    op.create_table(
        'broadcast_campaigns',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('title', sa.String(length=100), nullable=False),
        sa.Column('message_text', sa.Text(), nullable=False),
        sa.Column(
            'target_segment',
            sa.Enum(
                'trial', 'paid', 'trial_expiring_24h', 'trial_expiring_1h',
                'expired', 'inactive_7d', 'with_balance', 'all',
                name='broadcast_segment',
                native_enum=False, length=30,
            ),
            nullable=False,
        ),
        sa.Column(
            'status',
            sa.Enum(
                'draft', 'sending', 'completed', 'canceled', 'failed',
                name='broadcast_status',
                native_enum=False, length=20,
            ),
            nullable=False,
            server_default='draft',
        ),
        sa.Column('created_by_tg_id', sa.BigInteger(), nullable=False),
        sa.Column('total_recipients', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sent_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('blocked_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    # Индекс для листинга: чаще всего фильтруем по статусу и сортируем по created_at.
    op.create_index(
        'ix_broadcast_campaigns_status_created',
        'broadcast_campaigns', ['status', 'created_at'],
    )

    # ─── broadcast_deliveries ────────────────────────────
    op.create_table(
        'broadcast_deliveries',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('campaign_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('user_tg_id', sa.BigInteger(), nullable=False),
        sa.Column(
            'status',
            sa.Enum(
                'pending', 'sent', 'failed', 'blocked',
                name='delivery_status',
                native_enum=False, length=20,
            ),
            nullable=False,
            server_default='pending',
        ),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['campaign_id'], ['broadcast_campaigns.id'], ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'], ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    # Статистика по кампании — частый запрос "сколько sent/failed/blocked".
    op.create_index(
        'ix_broadcast_deliveries_campaign_status',
        'broadcast_deliveries', ['campaign_id', 'status'],
    )
    # user_tg_id нужен для быстрого поиска "когда этому юзеру слали".
    op.create_index(
        'ix_broadcast_deliveries_user_tg_id',
        'broadcast_deliveries', ['user_tg_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_broadcast_deliveries_user_tg_id', table_name='broadcast_deliveries')
    op.drop_index('ix_broadcast_deliveries_campaign_status', table_name='broadcast_deliveries')
    op.drop_table('broadcast_deliveries')
    op.drop_index('ix_broadcast_campaigns_status_created', table_name='broadcast_campaigns')
    op.drop_table('broadcast_campaigns')
