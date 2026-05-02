# 🌊 AquaSim — Low-Latency Event-Driven Trading Simulation Platform

A production-style trading simulation platform with real-time market data streaming,
plug-and-play strategy modules, sophisticated order book management, and a live
dashboard — all running in Docker.

---

## Architecture

```
Market Data Simulator
        │
        ▼  (Kafka: market_ticks)
Strategy Engine  ──────────────────────────────────────────────────────────────
  ├── MomentumStrategy (EMA crossover)                                        │
  └── MeanReversionStrategy (Bollinger Bands)                                 │
        │                                                                     │
        ▼  (Risk Manager check)                                               │
Execution Simulator  ◄─── LatencySimulator (Gaussian + tail-spike model)     │
        │                                                                     │
        ▼  (Trade fill)                                                       │
PnL Tracker → Redis (positions, equity curve)                                 │
        │                                                                     │
        ▼  (Kafka: trades, positions)                                         │
PostgreSQL (persistent trade/order log)                                       │
        │                                                                     │
        ▼                                                                     │
FastAPI (REST + WebSocket) ◄── Redis pub/sub ◄─────────────────────────────┘
        │
        ▼
React Dashboard (live charts, order book, PnL, risk, trade log)
```

---

## Stack

| Layer | Technology |
|---|---|
| Core engine | Python 3.11 + asyncio + uvloop |
| Event streaming | Apache Kafka (Confluent) |
| In-memory state | Redis 7 |
| Persistence | PostgreSQL 15 + SQLAlchemy async |
| API | FastAPI + WebSocket |
| Frontend | React 18 + TypeScript + Recharts |
| Infrastructure | Docker + Docker Compose |

---

## Quick Start

### 1. Prerequisites
- Docker Desktop ≥ 24
- Docker Compose ≥ 2.20

### 2. Clone and configure

```bash
git clone <repo>
cd aquasim
cp .env.example .env
```

### 3. Launch the full stack

```bash
docker compose up --build
```

Services start in dependency order. The engine waits for Kafka, Redis, and Postgres
to be healthy before starting.

| Service | URL |
|---|---|
| Dashboard | http://localhost:3000 |
| API docs (Swagger) | http://localhost:8000/docs |
| API health | http://localhost:8000/health |
| Kafka | localhost:29092 |
| Redis | localhost:6379 |
| Postgres | localhost:5432 |

### 4. Run in backtest mode

```bash
# First generate synthetic historical data
python scripts/seed_backtest_data.py --rows 100000 --symbol AAPL

# Then start with backtest mode
MODE=backtest docker compose up --build
```

---

## Project Structure

```
aquasim/
├── docker-compose.yml
├── .env.example
├── engine/                        # Core trading engine (Python async)
│   ├── core/
│   │   ├── config.py             # Pydantic settings
│   │   ├── engine.py             # Main orchestrator
│   │   └── event_bus.py          # Intra-process async event bus
│   ├── models/                   # Tick, Order, Trade, Position dataclasses
│   ├── orderbook/                # L2 order book with depth levels
│   ├── strategies/
│   │   ├── base.py               # Abstract BaseStrategy
│   │   ├── momentum.py           # EMA crossover strategy
│   │   └── mean_reversion.py     # Bollinger Band strategy
│   ├── execution/
│   │   ├── simulator.py          # Order matching engine
│   │   └── latency.py            # Gaussian + tail-spike latency model
│   ├── risk/                     # Pre-trade risk checks
│   ├── pnl/                      # Real-time PnL + equity curve
│   ├── kafka/                    # aiokafka producer/consumer wrappers
│   ├── redis_client/             # aioredis wrapper with typed key helpers
│   ├── db/                       # SQLAlchemy async models + sessions
│   └── data/
│       ├── simulator.py          # GBM synthetic market data generator
│       └── backtest_loader.py    # CSV historical data replayer
├── api/                          # FastAPI backend
│   ├── main.py                   # App + WebSocket endpoints
│   ├── routers/                  # REST endpoints per domain
│   ├── websocket/                # Redis pub/sub → WebSocket fan-out
│   └── services/                 # Service layer (Redis + DB reads)
├── frontend/                     # React + TypeScript dashboard
│   └── src/
│       ├── components/
│       │   ├── PriceChart        # Live candlestick/line chart
│       │   ├── PnLChart          # Strategy equity curve
│       │   ├── OrderBook         # L2 heatmap
│       │   ├── Positions         # Open position table
│       │   ├── TradeLog          # Real-time trade stream
│       │   └── RiskMetrics       # Drawdown + limits
│       └── hooks/useWebSocket    # Auto-reconnecting WebSocket hook
├── migrations/                   # Alembic schema migrations
└── scripts/
    ├── init_kafka_topics.py      # One-time Kafka topic creation
    └── seed_backtest_data.py     # Generate synthetic CSV for backtesting
```

---

## Adding a New Strategy

1. Create `engine/strategies/my_strategy.py`:

```python
from engine.strategies.base import BaseStrategy
from engine.models import Tick

class MyStrategy(BaseStrategy):
    async def on_tick(self, tick: Tick) -> None:
        # Your signal logic here
        if some_signal:
            await self.buy(tick.symbol, quantity=100.0)
```

2. Register it in `engine/core/engine.py`:

```python
self._register_strategy(
    MyStrategy(
        strategy_id="my_strategy_v1",
        symbols=["AAPL"],
        order_callback=self._on_order,
    )
)
```

No other changes needed. Risk, execution, PnL, persistence, and dashboard updates
are all handled automatically.

---

## Configuration

All settings are in `engine/core/config.py` and can be overridden via environment
variables (or `.env`):

| Variable | Default | Description |
|---|---|---|
| `MODE` | `live` | `live` or `backtest` |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:29092` | Kafka broker |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection |
| `DATABASE_URL` | see config | Postgres asyncpg URL |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` |

Strategy-level parameters (window sizes, trade quantities, risk limits) are set
directly in the constructor calls in `engine/core/engine.py`.

---

## Risk Limits

Per-strategy pre-trade checks (configurable in `config.py`):

| Limit | Default |
|---|---|
| Max position notional | $100,000 |
| Max drawdown | 5% |
| Max daily loss | $5,000 |

Orders breaching any limit are rejected immediately and published to the
`risk_events` Redis channel (visible in the dashboard).

---

## Latency Model

The execution simulator uses a log-normal + tail-spike latency model:

- Base: 500µs median
- Jitter: ±200µs Gaussian
- Tail spikes: 1% probability, 10× multiplier (~5ms)

Latency is displayed per-trade in the Trade Log panel.
