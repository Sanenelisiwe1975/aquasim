"""Initial schema

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'trades',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('order_id', sa.String(36), nullable=False),
        sa.Column('strategy_id', sa.String(64), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('side', sa.String(4), nullable=False),
        sa.Column('quantity', sa.Float, nullable=False),
        sa.Column('price', sa.Float, nullable=False),
        sa.Column('notional', sa.Float, nullable=False),
        sa.Column('latency_us', sa.Integer, nullable=False),
        sa.Column('slippage', sa.Float, nullable=False),
        sa.Column('timestamp', sa.DateTime, nullable=False),
        sa.Column('created_at', sa.DateTime),
    )
    op.create_index('ix_trades_strategy_id', 'trades', ['strategy_id'])
    op.create_index('ix_trades_symbol', 'trades', ['symbol'])
    op.create_index('ix_trades_timestamp', 'trades', ['timestamp'])
    op.create_index('ix_trades_strategy_ts', 'trades', ['strategy_id', 'timestamp'])

    op.create_table(
        'orders',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('strategy_id', sa.String(64), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('side', sa.String(4), nullable=False),
        sa.Column('quantity', sa.Float, nullable=False),
        sa.Column('order_type', sa.String(10), nullable=False),
        sa.Column('limit_price', sa.Float, nullable=True),
        sa.Column('status', sa.String(12), nullable=False),
        sa.Column('filled_price', sa.Float, nullable=True),
        sa.Column('filled_quantity', sa.Float, nullable=True),
        sa.Column('rejection_reason', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False),
        sa.Column('submitted_at', sa.DateTime, nullable=True),
        sa.Column('filled_at', sa.DateTime, nullable=True),
    )
    op.create_index('ix_orders_strategy_id', 'orders', ['strategy_id'])
    op.create_index('ix_orders_status', 'orders', ['status'])

    op.create_table(
        'backtest_runs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('strategy_id', sa.String(64), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('start_time', sa.DateTime, nullable=False),
        sa.Column('end_time', sa.DateTime, nullable=True),
        sa.Column('total_trades', sa.Integer, default=0),
        sa.Column('realized_pnl', sa.Float, default=0.0),
        sa.Column('max_drawdown', sa.Float, default=0.0),
        sa.Column('sharpe_ratio', sa.Float, nullable=True),
        sa.Column('win_rate', sa.Float, nullable=True),
        sa.Column('config_json', sa.Text, nullable=True),
        sa.Column('completed', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime),
    )

    op.create_table(
        'ticks',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('price', sa.Float, nullable=False),
        sa.Column('bid', sa.Float, nullable=False),
        sa.Column('ask', sa.Float, nullable=False),
        sa.Column('bid_size', sa.Float, nullable=False),
        sa.Column('ask_size', sa.Float, nullable=False),
        sa.Column('volume', sa.Float, nullable=False),
        sa.Column('timestamp', sa.DateTime, nullable=False),
        sa.Column('sequence', sa.Integer, nullable=False),
    )
    op.create_index('ix_ticks_symbol', 'ticks', ['symbol'])
    op.create_index('ix_ticks_timestamp', 'ticks', ['timestamp'])
    op.create_index('ix_ticks_symbol_ts', 'ticks', ['symbol', 'timestamp'])


def downgrade() -> None:
    op.drop_table('ticks')
    op.drop_table('backtest_runs')
    op.drop_table('orders')
    op.drop_table('trades')
