"""Add realized_pnl to trades table

Revision ID: 002
Revises: 001
Create Date: 2026-05-03 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'trades',
        sa.Column('realized_pnl', sa.Float, nullable=False, server_default='0.0'),
    )


def downgrade() -> None:
    op.drop_column('trades', 'realized_pnl')
