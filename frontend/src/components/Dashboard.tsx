import React, { useState, useCallback, useEffect, useRef } from 'react';
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

export const Dashboard: React.FC = () => {
  const [selectedSymbol, setSelectedSymbol] = useState('AAPL');
  const [ticks, setTicks] = useState<Record<string, Tick[]>>({});
  const [book, setBook] = useState<OrderBook | null>(null);
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

    fetch(`${API}/orderbook/${selectedSymbol}`)
      .then((r) => r.ok ? r.json() : null)
      .then((d) => d && setBook(d))
      .catch(() => {});

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

      // Update equity curve
      const sid = pos.strategy_id;
      const point: EquityPoint = { timestamp: pos.last_updated, total_pnl: pos.total_pnl };
      setEquityCurves((prev) => ({
        ...prev,
        [sid]: [...(prev[sid] ?? []), point].slice(-500),
      }));
    }
  }, []);

  useWebSocket(WS_URL, handleMessage);

  // ── Poll ticks & book for selected symbol every 500ms ─────────────────
  useEffect(() => {
    const id = setInterval(async () => {
      const [ticksR, bookR] = await Promise.all([
        fetch(`${API}/orderbook/${selectedSymbol}/ticks?n=200`).catch(() => null),
        fetch(`${API}/orderbook/${selectedSymbol}`).catch(() => null),
      ]);
      if (ticksR?.ok) {
        const data: Tick[] = await ticksR.json();
        setTicks((prev) => ({ ...prev, [selectedSymbol]: data }));
      }
      if (bookR?.ok) {
        setBook(await bookR.json());
      }
    }, 500);
    return () => clearInterval(id);
  }, [selectedSymbol]);

  const symTicks = ticks[selectedSymbol] ?? [];

  return (
    <div style={{ minHeight: '100vh', background: 'var(--color-bg)', padding: 16 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 20, fontWeight: 700, letterSpacing: '-0.5px' }}>
            🌊 AquaSim
          </span>
          <span style={{ fontSize: 11, color: 'var(--color-muted)', background: '#21262d', padding: '2px 8px', borderRadius: 12 }}>
            Trading Simulation Platform
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            width: 8, height: 8, borderRadius: '50%',
            background: wsStatus === 'live' ? 'var(--color-green)' : wsStatus === 'connecting' ? 'var(--color-yellow)' : 'var(--color-red)',
          }} />
          <span style={{ fontSize: 11, color: 'var(--color-muted)' }}>
            {wsStatus === 'live' ? 'Live' : wsStatus === 'connecting' ? 'Connecting…' : 'Offline'}
          </span>
        </div>
      </div>

      {/* Symbol selector */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {SYMBOLS.map((s) => (
          <button
            key={s}
            onClick={() => setSelectedSymbol(s)}
            style={{
              padding: '4px 14px',
              borderRadius: 6,
              border: '1px solid var(--color-border)',
              background: selectedSymbol === s ? 'var(--color-blue)' : 'var(--color-surface)',
              color: selectedSymbol === s ? '#fff' : 'var(--color-muted)',
              cursor: 'pointer',
              fontFamily: 'JetBrains Mono',
              fontWeight: 600,
              fontSize: 12,
            }}
          >
            {s}
          </button>
        ))}
      </div>

      {/* Row 1: Price chart + Order book */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: 12, marginBottom: 12 }}>
        <PriceChart ticks={symTicks} symbol={selectedSymbol} />
        <OrderBookPanel book={book} />
      </div>

      {/* Row 2: PnL charts */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
        {STRATEGIES.map((sid) => (
          <PnLChart key={sid} strategyId={sid} data={equityCurves[sid] ?? []} />
        ))}
      </div>

      {/* Row 3: Risk */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
        {STRATEGIES.map((sid) => (
          <RiskMetrics key={sid} strategyId={sid} risk={risk[sid] ?? null} />
        ))}
      </div>

      {/* Row 4: Positions */}
      <div style={{ marginBottom: 12 }}>
        <PositionsTable positions={positions} />
      </div>

      {/* Row 5: Trade log */}
      <TradeLog trades={trades} />
    </div>
  );
};
