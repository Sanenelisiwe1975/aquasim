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


SYMBOLS = {
    "AAPL": 182.0,
    "MSFT": 374.0,
    "GOOGL": 140.0,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=20_000,
                        help="Rows per symbol (default 20000 → ~60k total)")
    parser.add_argument("--out", type=str, default="data/backtest_data.csv")
    args = parser.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    all_records: list = []
    for symbol, start_price in SYMBOLS.items():
        records = generate(symbol, args.rows, start_price=start_price)
        all_records.extend(records)
        print(f"  {symbol}: {len(records)} rows (start ${start_price})")

    # Interleave by timestamp so the replayer sees a realistic mixed stream
    all_records.sort(key=lambda r: r["timestamp"])

    fieldnames = ["timestamp", "symbol", "price", "bid", "ask", "bid_size", "ask_size", "volume"]
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_records)

    print(f"Written {len(all_records)} rows to {out}")


if __name__ == "__main__":
    main()
