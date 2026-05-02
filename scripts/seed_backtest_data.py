"""
Generates a synthetic historical CSV for backtesting.
Output: engine/data/backtest_data.csv

Usage:
  python scripts/seed_backtest_data.py [--rows 50000] [--symbol AAPL]
"""
import argparse
import csv
import math
import random
from datetime import datetime, timedelta
from pathlib import Path


def generate(symbol: str, rows: int, start_price: float = 100.0) -> list:
    records = []
    price = start_price
    ts = datetime(2024, 1, 2, 9, 30, 0)
    vol = 0.001
    spread_bps = 2.0

    for i in range(rows):
        shock = random.gauss(0, 1)
        price = price * math.exp((-0.5 * vol ** 2) * 0.1 + vol * math.sqrt(0.1) * shock)
        half_spread = price * (spread_bps / 10_000) / 2.0
        bid = price - half_spread
        ask = price + half_spread
        records.append({
            "timestamp": ts.isoformat(),
            "symbol": symbol,
            "price": round(price, 6),
            "bid": round(bid, 6),
            "ask": round(ask, 6),
            "bid_size": round(random.uniform(50, 500), 2),
            "ask_size": round(random.uniform(50, 500), 2),
            "volume": round(random.uniform(10, 200), 2),
        })
        ts += timedelta(milliseconds=100)

    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=50_000)
    parser.add_argument("--symbol", type=str, default="AAPL")
    args = parser.parse_args()

    out = Path("engine/data/backtest_data.csv")
    out.parent.mkdir(parents=True, exist_ok=True)

    records = generate(args.symbol, args.rows)
    fieldnames = ["timestamp", "symbol", "price", "bid", "ask", "bid_size", "ask_size", "volume"]

    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    print(f"Written {len(records)} rows to {out}")


if __name__ == "__main__":
    main()
