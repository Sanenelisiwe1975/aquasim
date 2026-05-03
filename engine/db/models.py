"""SQLAlchemy ORM models for persistent storage."""
from datetime import datetime
from sqlalchemy import (
    Column, String, Float, Integer, DateTime, Text, Boolean, Index
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class TradeRecord(Base):
    __tablename__ = "trades"

    id = Column(String(36), primary_key=True)
    order_id = Column(String(36), nullable=False, index=True)
    strategy_id = Column(String(64), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(String(4), nullable=False)
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    notional = Column(Float, nullable=False)
    latency_us = Column(Integer, nullable=False)
    slippage = Column(Float, nullable=False)
    realized_pnl = Column(Float, nullable=False, default=0.0)
    timestamp = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_trades_strategy_ts", "strategy_id", "timestamp"),
    )


class OrderRecord(Base):
    __tablename__ = "orders"

    id = Column(String(36), primary_key=True)
    strategy_id = Column(String(64), nullable=False, index=True)
    symbol = Column(String(20), nullable=False)
    side = Column(String(4), nullable=False)
    quantity = Column(Float, nullable=False)
    order_type = Column(String(10), nullable=False)
    limit_price = Column(Float, nullable=True)
    status = Column(String(12), nullable=False, index=True)
    filled_price = Column(Float, nullable=True)
    filled_quantity = Column(Float, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False)
    submitted_at = Column(DateTime, nullable=True)
    filled_at = Column(DateTime, nullable=True)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id = Column(String(36), primary_key=True)
    strategy_id = Column(String(64), nullable=False)
    symbol = Column(String(20), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    total_trades = Column(Integer, default=0)
    realized_pnl = Column(Float, default=0.0)
    max_drawdown = Column(Float, default=0.0)
    sharpe_ratio = Column(Float, nullable=True)
    win_rate = Column(Float, nullable=True)
    config_json = Column(Text, nullable=True)
    completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class TickRecord(Base):
    """Stored only during backtest runs for replay."""
    __tablename__ = "ticks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    price = Column(Float, nullable=False)
    bid = Column(Float, nullable=False)
    ask = Column(Float, nullable=False)
    bid_size = Column(Float, nullable=False)
    ask_size = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    sequence = Column(Integer, nullable=False)

    __table_args__ = (
        Index("ix_ticks_symbol_ts", "symbol", "timestamp"),
    )
