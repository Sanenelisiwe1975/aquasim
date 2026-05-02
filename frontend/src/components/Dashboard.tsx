import React, { useState, useCallback, useEffect } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';
import { PriceChart } from './PriceChart';
import { PnLChart } from './PnLChart';
import { OrderBookPanel } from './OrderBook';
import { PositionsTable } from './Positions';
import { TradeLog } from './TradeLog';
import { RiskMetrics } from './RiskMetrics';
import { Tick, Trade, Position, OrderBook, RiskSummary, EquityPoint, WsMessage } from '../types';

const API = '/api/v1';
const WS_URL = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws`;
const SYMBOLS = ['AAPL', 'MSFT', 'GOOGL'];
const STRATEGIES = ['momentum_v1', 'mean_rev_v1'];
const MAX_TICKS = 200;
const MAX_TRADES = 100;

const WS_DOT_COLOR: Record<string, string> = {
  live: 'var(--color-green)',
  connecting: 'var(--color-yellow)',
  offline: 'var(--color-red)',
};

export const Dashboard: React.FC = () => {
  const [selectedSymbol, setSelectedSymbol] = useState('AAPL');
  const [ticks, setTicks] = useState<Record<string, Tick[]>>({});
  const [books, setBooks] = useState<Record<string, OrderBook>>({});
  const [positions, setPositions] = useState<Position[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [risk, setRisk] = useState<Record<string, RiskSummary>>({});
  const [equityCurves, setEquityCurves] = useState<Record<string, EquityPoint[]>>({});
  const [wsStatus, setWsStatus] = useState<'connecting' | 'live' | 'offline'>('connecting');

  // ── Bootstrap: load initial data from REST ─────────────────────────────
  useEffect(() => {
    SYMBOLS.forEach(async (sym) => {
      const r = await fetch(`${API}/orderbook/${sym}/ticks?n=200`).catch(() => null);
      if (r?.ok) {
        const data: Tick[] = await r.json();
        setTicks((prev) => ({ ...prev, [sym]: data }));
      }
    });

    // Seed order books so the panel isn't blank while WS warms up
    SYMBOLS.forEach(async (sym) => {
      const r = await fetch(`${API}/orderbook/${sym}`).catch(() => null);
      if (r?.ok) {
        const data: OrderBook = await r.json();
        setBooks((prev) => ({ ...prev, [sym]: data }));
      }
    });

    fetch(`${API}/positions/`)
      .then((r) => r.ok ? r.json() : null)
      .then((d) => {
        if (d) {
          const flat: Position[] = Object.values(d as Record<string, Position[]>).flat();
          setPositions(flat);
        }
      })
      .catch(() => {});

    fetch(`${API}/trades/?limit=50`)
      .then((r) => r.ok ? r.json() : null)
      .then((d) => d && setTrades(d))
      .catch(() => {});

    STRATEGIES.forEach(async (sid) => {
      const [riskR, curveR] = await Promise.all([
        fetch(`${API}/strategies/${sid}/risk`).catch(() => null),
        fetch(`${API}/positions/${sid}/equity-curve?n=300`).catch(() => null),
      ]);
      if (riskR?.ok) setRisk((p) => ({ ...p, [sid]: await riskR.json() }));
      if (curveR?.ok) setEquityCurves((p) => ({ ...p, [sid]: await curveR.json() }));
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── WebSocket live feed ────────────────────────────────────────────────
  // All setters use functional form — no state captured in closure.
  const handleMessage = useCallback((raw: unknown) => {
    const msg = raw as WsMessage;
    setWsStatus('live');
    const ch = msg._channel as string;

    if (ch === 'trades') {
      const t = msg as unknown as Trade;
      setTrades((prev) => [t, ...prev].slice(0, MAX_TRADES));
    }

    if (ch?.startsWith('positions:')) {
      const pos = msg as unknown as Position;
      setPositions((prev) => {
        const idx = prev.findIndex(
          (p) => p.strategy_id === pos.strategy_id && p.symbol === pos.symbol
        );
        if (idx >= 0) {
          const next = [...prev];
          next[idx] = pos;
          return next;
        }
        return [pos, ...prev];
      });
      const sid = pos.strategy_id;
      const point: EquityPoint = { timestamp: pos.last_updated, total_pnl: pos.total_pnl };
      setEquityCurves((prev) => ({
        ...prev,
        [sid]: [...(prev[sid] ?? []), point].slice(-500),
      }));
    }

    if (ch?.startsWith('orderbook:')) {
      const sym = ch.split(':')[1];
      setBooks((prev) => ({ ...prev, [sym]: msg as unknown as OrderBook }));
    }

    if (ch?.startsWith('ticks:')) {
      const sym = ch.split(':')[1];
      const tick = msg as unknown as Tick;
      setTicks((prev) => ({
        ...prev,
        [sym]: [tick, ...(prev[sym] ?? [])].slice(0, MAX_TICKS),
      }));
    }
  }, []);

  useWebSocket(WS_URL, handleMessage);

  const symTicks = ticks[selectedSymbol] ?? [];
  const book = books[selectedSymbol] ?? null;

  return (
    <div className="dashboard">
      {/* Header */}
      <div className="dashboard-header">
        <div className="dashboard-title-group">
          <span className="dashboard-title">🌊 AquaSim</span>
          <span className="dashboard-subtitle">Trading Simulation Platform</span>
        </div>
        <div className="dashboard-ws-indicator">
          <div className="ws-dot" style={{ background: WS_DOT_COLOR[wsStatus] }} />
          <span className="ws-label">
            {wsStatus === 'live' ? 'Live' : wsStatus === 'connecting' ? 'Connecting…' : 'Offline'}
          </span>
        </div>
      </div>

      {/* Symbol selector */}
      <div className="symbol-bar">
        {SYMBOLS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setSelectedSymbol(s)}
            className="symbol-btn"
            style={{
              background: selectedSymbol === s ? 'var(--color-blue)' : 'var(--color-surface)',
              color: selectedSymbol === s ? '#fff' : 'var(--color-muted)',
            }}
          >
            {s}
          </button>
        ))}
      </div>

      {/* Row 1: Price chart + Order book */}
      <div className="grid-chart-row">
        <PriceChart ticks={symTicks} symbol={selectedSymbol} />
        <OrderBookPanel book={book} />
      </div>

      {/* Row 2: PnL charts */}
      <div className="grid-2col">
        {STRATEGIES.map((sid) => (
          <PnLChart key={sid} strategyId={sid} data={equityCurves[sid] ?? []} />
        ))}
      </div>

      {/* Row 3: Risk */}
      <div className="grid-2col">
        {STRATEGIES.map((sid) => (
          <RiskMetrics key={sid} strategyId={sid} risk={risk[sid] ?? null} />
        ))}
      </div>

      {/* Row 4: Positions */}
      <div className="section">
        <PositionsTable positions={positions} />
      </div>

      {/* Row 5: Trade log */}
      <TradeLog trades={trades} />
    </div>
  );
};
