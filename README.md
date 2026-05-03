# 🌊 AquaSim — Low-Latency Event-Driven Trading Simulation Platform

A production-style trading simulation platform with real-time market data streaming,
plug-and-play strategy modules, a sophisticated order book, and a live dashboard —
all running in Docker.

---

## Architecture

```
Market Data Simulator / Backtest CSV Replayer
        │
        ▼  (Kafka: market_ticks)
Strategy Engine ────────────────────────────────────────────────────────────────
  ├── MomentumStrategy   (EMA crossover)                                       │
  └── MeanReversionStrategy (Bollinger Bands)                                  │
        │                                                                      │
        ▼  Risk Manager (notional / drawdown / daily-loss limits)              │
Execution Simulator                                                            │
  ├── Latency model: Gaussian + 1% tail-spike                                  │
  ├── Slippage: book-walk + spread cost + latency adverse move                 │
  └── Limit order queue (re-checked on every tick, 60-tick TTL)                │
        │                                                                      │
        ▼  (Trade fill)                                                        │
PnL Tracker  →  Redis (positions, equity curve sampled at 1 Hz)                │
        │                                                                      │
        ▼  (Kafka: trades, orders)                                             │
PostgreSQL  (trades, orders, backtest_runs — managed by Alembic)               │
        │                                                                      │
        ▼                                                                      │
FastAPI REST + WebSocket  ◄── Redis pub/sub (pattern: positions:*, orderbook:*,│
        │                     ticks:*, risk:*, trades, risk_events)  ◄─────────┘
        │
        ▼
React Dashboard
  ├── Live price chart + order book heatmap
  ├── Dual-line PnL chart (total + realized)
  ├── Risk monitor with drawdown + daily-loss bars
  ├── Sortable / filterable positions table
  └── Trade log with per-trade PnL

Runtime control via engine_commands Redis channel:
  POST /api/v1/orders          — manual order entry
  POST /strategies/{id}/pause  — pause strategy
  POST /strategies/{id}/resume — resume strategy
  PATCH /strategies/{id}/risk  — override risk limits at runtime
  POST /positions/{id}/{sym}/liquidate — flatten position
```

---

## Stack

| Layer | Technology |
|---|---|
| Core engine | Python 3.11 + asyncio + uvloop |
| Event streaming | Apache Kafka (Confluent) |
| In-memory state | Redis 7 (pub/sub + key-value) |
| Persistence | PostgreSQL 15 + SQLAlchemy async + Alembic |
| API | FastAPI + WebSocket |
| Frontend | React 18 + TypeScript + Recharts |
| Infrastructure | Docker + Docker Compose |

---

## Quick Start

### Prerequisites
- Docker Desktop ≥ 24
- Docker Compose ≥ 2.20

### 1. Configure

```bash
git clone <repo>
cd aquasim
cp .env.example .env
# Edit .env if you want non-default Postgres credentials
```

### 2. Launch

```bash
docker compose up --build
```

Services start in dependency order. Kafka, Redis, and Postgres must be healthy
before the engine starts.

| Service | URL |
|---|---|
| Dashboard | http://localhost:3000 |
| API docs | http://localhost:8000/docs |
| API health | http://localhost:8000/health |

### 3. Backtest mode

```bash
# Generate synthetic historical data for all three symbols
python scripts/seed_backtest_data.py --rows 20000   # → data/backtest_data.csv

# Start in backtest mode (engine replays the CSV then saves metrics to Postgres)
MODE=backtest docker compose up --build
```

Results appear in `GET /api/v1/backtest/runs`.

---

## Project Structure

```
aquasim/
├── .env.example                   # Required env vars with defaults
├── docker-compose.yml             # Full stack (mounts data/ and migrations/)
├── data/                          # Generated backtest CSV (git-ignored)
│
├── engine/                        # Python async trading engine
│   ├── core/
│   │   ├── config.py              # Pydantic settings (env-var overrideable)
│   │   └── engine.py              # Orchestrator + engine_commands listener
│   ├── backtest/
│   │   └── metrics.py             # Sharpe, win rate, max drawdown
│   ├── models/                    # Tick, Order, Trade, Position dataclasses
│   ├── orderbook/                 # L2 order book (depth + market impact)
│   ├── strategies/
│   │   ├── base.py                # BaseStrategy (pause/resume support)
│   │   ├── momentum.py            # EMA crossover (net-quantity reversal)
│   │   └── mean_reversion.py      # Bollinger Bands (net-quantity reversal)
│   ├── execution/
│   │   ├── simulator.py           # Order matching + limit order queue
│   │   └── latency.py             # Gaussian + tail-spike latency model
│   ├── risk/                      # Pre-trade checks + runtime overrides
│   ├── pnl/                       # Real-time PnL + 1 Hz equity curve
│   ├── kafka/                     # aiokafka producer/consumer
│   ├── redis_client/              # aioredis typed key helpers
│   ├── db/                        # SQLAlchemy async + Alembic init
│   └── data/
│       ├── simulator.py           # GBM synthetic data generator
│       └── backtest_loader.py     # CSV replayer (publishes to pub/sub)
│
├── api/                           # FastAPI
│   ├── routers/
│   │   ├── orders.py              # GET/POST /orders, GET /orders/{id}
│   │   ├── trades.py              # GET /trades, GET /trades/stats (win rate)
│   │   ├── positions.py           # GET /positions, POST /{id}/{sym}/liquidate
│   │   ├── strategies.py          # pause, resume, PATCH risk limits
│   │   ├── orderbook.py           # L2 snapshot + tick history
│   │   └── backtest.py            # Backtest run results
│   └── websocket/
│       └── manager.py             # Redis pub/sub → WebSocket fan-out
│
├── frontend/                      # React + TypeScript
│   └── src/
│       ├── components/
│       │   ├── PriceChart.tsx     # Live price + bid/ask lines
│       │   ├── PnLChart.tsx       # Total PnL (filled) + Realized PnL (dashed)
│       │   ├── OrderBook.tsx      # L2 heatmap with live updates
│       │   ├── Positions.tsx      # Sortable + filterable position table
│       │   ├── TradeLog.tsx       # Trade stream with per-trade PnL column
│       │   ├── RiskMetrics.tsx    # Drawdown + daily-loss utilisation bars
│       │   └── Dashboard.tsx      # Layout + WS handler + toast alerts
│       └── hooks/useWebSocket.ts  # Auto-reconnecting WebSocket
│
├── migrations/                    # Alembic schema migrations
│   └── versions/
│       ├── 001_initial_schema.py
│       └── 002_add_trade_realized_pnl.py
│
└── scripts/
    ├── init_kafka_topics.py       # One-time Kafka topic creation
    └── seed_backtest_data.py      # Generates data/backtest_data.csv
```

---

## Adding a New Strategy

1. Create `engine/strategies/my_strategy.py`:

```python
from engine.strategies.base import BaseStrategy
from engine.models import Tick

class MyStrategy(BaseStrategy):
    async def on_tick(self, tick: Tick) -> None:
        if some_signal:
            await self.buy(tick.symbol, quantity=100.0)
        elif other_signal:
            await self.sell(tick.symbol, quantity=100.0)
```

2. Register in `engine/core/engine.py`:

```python
self._register_strategy(
    MyStrategy(
        strategy_id="my_strat_v1",
        symbols=SYMBOLS,
        order_callback=self._on_order,
    )
)
```

Risk checks, execution, PnL tracking, persistence, WebSocket streaming, and
dashboard updates are all wired automatically. No other changes needed.

---

## REST API

### Orders

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/orders/` | List orders (filters: strategy_id, symbol, status, from_ts, to_ts; pagination: limit, offset) |
| `GET` | `/api/v1/orders/{id}` | Get order with fill details |
| `POST` | `/api/v1/orders/` | Submit manual order (async fill, returns order_id immediately) |

### Positions

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/positions/` | All positions by strategy |
| `GET` | `/api/v1/positions/{strategy_id}` | Positions for one strategy |
| `GET` | `/api/v1/positions/{strategy_id}/equity-curve` | Equity curve (total + realized PnL) |
| `POST` | `/api/v1/positions/{strategy_id}/{symbol}/liquidate` | Flatten position at market |

### Strategies

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/strategies/` | Registered strategy IDs |
| `GET` | `/api/v1/strategies/{id}/risk` | Current risk metrics |
| `GET` | `/api/v1/strategies/{id}/status` | Paused / running |
| `POST` | `/api/v1/strategies/{id}/pause` | Stop strategy emitting orders |
| `POST` | `/api/v1/strategies/{id}/resume` | Resume strategy |
| `PATCH` | `/api/v1/strategies/{id}/risk` | Override limits at runtime |

### Trades

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/trades/` | Trade history (filters: strategy_id, symbol, from_ts, to_ts; pagination: limit, offset) |
| `GET` | `/api/v1/trades/stats/{strategy_id}` | Win rate, total PnL, per-symbol breakdown |

### Backtest

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/backtest/runs` | List completed backtest runs |
| `GET` | `/api/v1/backtest/runs/{id}` | Run detail (Sharpe, win rate, drawdown) |

---

## WebSocket

Connect to `ws://localhost:8000/ws` (all channels) or `ws://localhost:8000/ws/{channel}`.

Every message includes a `_channel` field identifying its source:

| Channel pattern | Payload | Rate |
|---|---|---|
| `trades` | Trade fill (side, qty, price, latency, slippage, realized_pnl) | Per fill |
| `positions:{strategy_id}` | Position snapshot (qty, entry, PnL, notional) | Per tick (per open position) |
| `risk:{strategy_id}` | Risk summary (equity, drawdown %, daily PnL) | Per fill |
| `orderbook:{symbol}` | L2 book snapshot (top-10 bids/asks) | Per tick |
| `ticks:{symbol}` | Price tick (price, bid, ask, volume) | Per tick (~10 Hz/symbol) |
| `risk_events` | Order rejection or limit expiry | On event |

The manager uses Redis `PSUBSCRIBE` for pattern channels — new strategies and
symbols are picked up automatically without any code changes.

---

## Configuration

All settings live in `engine/core/config.py` and are overrideable via environment variables:

| Variable | Default | Description |
|---|---|---|
| `MODE` | `live` | `live` (GBM) or `backtest` (CSV replay) |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:29092` | Kafka broker address |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection string |
| `DATABASE_URL` | see config | PostgreSQL asyncpg URL |
| `MIGRATIONS_DIR` | auto-detected | Path to `migrations/` directory (set to `/app/migrations` in Docker) |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` |

Strategy parameters (EMA windows, Bollinger window, trade quantities) are set
directly in the constructor calls in `engine/core/engine.py`.

---

## Risk Limits

Per-strategy pre-trade checks — configurable globally in `config.py` or overridden
per-strategy at runtime via `PATCH /api/v1/strategies/{id}/risk`:

| Limit | Default | Override field |
|---|---|---|
| Max position notional | $100,000 | `max_position_usd` |
| Max drawdown from peak | 5% | `max_drawdown_pct` |
| Max daily loss | $5,000 | `max_daily_loss_usd` |

Risk state (peak equity, daily PnL) persists across engine restarts via Redis.

---

## Execution & Slippage Model

- **Latency**: log-normal base (500 µs) + Gaussian jitter (±200 µs) + 1% tail spikes (10×)
- **Market orders**: walk the order book from best ask/bid; add a small adverse price
  move proportional to √latency to model execution risk
- **Limit orders**: queued and re-checked on every tick; expire after 60 ticks (~6 s)

---

## Schema Migrations

Alembic manages the schema. Migrations run automatically on engine startup:

```bash
# Run manually (local dev)
alembic -c migrations/alembic.ini upgrade head

# Check current revision
alembic -c migrations/alembic.ini current
```

The engine calls `alembic upgrade head` on every start (idempotent); it falls back
to SQLAlchemy `create_all` if Alembic cannot connect.
