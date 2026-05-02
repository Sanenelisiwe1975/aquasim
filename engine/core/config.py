from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Literal


class Settings(BaseSettings):
    # Kafka
    kafka_bootstrap_servers: str = Field("localhost:29092", env="KAFKA_BOOTSTRAP_SERVERS")
    kafka_consumer_group: str = "aquasim-engine"

    # Redis
    redis_url: str = Field("redis://localhost:6379", env="REDIS_URL")

    # Postgres
    database_url: str = Field(
        "postgresql+asyncpg://aquasim:aquasim_secret@localhost:5432/aquasim",
        env="DATABASE_URL",
    )

    # Engine mode
    mode: Literal["live", "backtest"] = Field("live", env="MODE")

    # Simulation parameters
    tick_interval_ms: float = 100          # ms between synthetic ticks
    initial_price: float = 100.0
    price_volatility: float = 0.001        # per-tick vol
    spread_bps: float = 2.0               # bid-ask spread in basis points
    orderbook_levels: int = 10            # depth of synthetic book

    # Latency model (microseconds)
    base_latency_us: int = 500
    latency_jitter_us: int = 200

    # Risk limits (per strategy)
    max_position_usd: float = 100_000.0
    max_drawdown_pct: float = 0.05        # 5 %
    max_daily_loss_usd: float = 5_000.0

    # Backtest
    backtest_file: str = "data/backtest_data.csv"
    backtest_speed_multiplier: float = 100.0  # replay 100x faster than real-time

    log_level: str = Field("INFO", env="LOG_LEVEL")

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
