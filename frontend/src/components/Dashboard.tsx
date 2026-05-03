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
const MAX_TICKS  = 200;
const MAX_TRADES = 100;
const ALERT_TTL  = 6000; // ms before auto-dismiss

interface RiskAlert {
  id: string;
  title: string;
  desc: string;
}


export const Dashboard: React.FC = () => {
  const [selectedSymbol, setSelectedSymbol] = useState('AAPL');
  const [ticks,        setTicks]        = useState<Record<string, Tick[]>>({});
  const [books,        setBooks]        = useState<Record<string, OrderBook>>({});
  const [positions,    setPositions]    = useState<Position[]>([]);
  const [trades,       setTrades]       = useState<Trade[]>([]);
  const [risk,         setRisk]         = useState<Record<string, RiskSummary>>({});
  const [equityCurves, setEquityCurves] = useState<Record<string, EquityPoint[]>>({});
  const [wsStatus,     setWsStatus]     = useState<'connecting' | 'live' | 'offline'>('connecting');
  const [alerts,       setAlerts]       = useState<RiskAlert[]>([]);
  const alertTimers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  // ── Bootstrap ──────────────────────────────────────────────────────────
  useEffect(() => {
    SYMBOLS.forEach(async (sym) => {
      const r = await fetch(`${API}/orderbook/${sym}/ticks?n=200`).catch(() => null);
      if (r?.ok) {
        const data: Tick[] = await r.json();
        setTicks((prev) => ({ ...prev, [sym]: data }));
      }
    });

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
        if (d) setPositions(Object.values(d as Record<string, Position[]>).flat());
      }).catch(() => {});

    fetch(`${API}/trades/?limit=50`)
      .then((r) => r.ok ? r.json() : null)
      .then((d) => d && setTrades(d))
      .catch(() => {});

    STRATEGIES.forEach(async (sid) => {
      const [riskR, curveR] = await Promise.all([
        fetch(`${API}/strategies/${sid}/risk`).catch(() => null),
        fetch(`${API}/positions/${sid}/equity-curve?n=300`).catch(() => null),
      ]);
      if (riskR?.ok)  setRisk((p)         => ({ ...p, [sid]: await riskR.json() }));
      if (curveR?.ok) setEquityCurves((p) => ({ ...p, [sid]: await curveR.json() }));
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Alert helpers ──────────────────────────────────────────────────────
  const dismissAlert = useCallback((id: string) => {
    setAlerts((prev) => prev.filter((a) => a.id !== id));
    const t = alertTimers.current.get(id);
    if (t) { clearTimeout(t); alertTimers.current.delete(id); }
  }, []);

  const pushAlert = useCallback((alert: RiskAlert) => {
    setAlerts((prev) => [alert, ...prev].slice(0, 5));
    const t = setTimeout(() => dismissAlert(alert.id), ALERT_TTL);
    alertTimers.current.set(alert.id, t);
  }, [dismissAlert]);

  // ── WebSocket live feed ────────────────────────────────────────────────
  const handleMessage = useCallback((raw: unknown) => {
    const msg = raw as WsMessage;
    setWsStatus('live');
    const ch = msg._channel as string;

    if (ch === 'trades') {
      setTrades((prev) => [msg as unknown as Trade, ...prev].slice(0, MAX_TRADES));
    }

    if (ch?.startsWith('positions:')) {
      const pos = msg as unknown as Position;
      setPositions((prev) => {
        const idx = prev.findIndex(
          (p) => p.strategy_id === pos.strategy_id && p.symbol === pos.symbol
        );
        if (idx >= 0) { const next = [...prev]; next[idx] = pos; return next; }
        return [pos, ...prev];
      });
      const sid = pos.strategy_id;
      const point: EquityPoint = {
        timestamp: pos.last_updated,
        total_pnl: pos.total_pnl,
        realized:  pos.realized_pnl,
      };
      setEquityCurves((prev) => ({ ...prev, [sid]: [...(prev[sid] ?? []), point].slice(-500) }));
    }

    if (ch?.startsWith('orderbook:')) {
      const sym = ch.split(':')[1];
      setBooks((prev) => ({ ...prev, [sym]: msg as unknown as OrderBook }));
    }

    if (ch?.startsWith('ticks:')) {
      const sym  = ch.split(':')[1];
      const tick = msg as unknown as Tick;
      setTicks((prev) => ({ ...prev, [sym]: [tick, ...(prev[sym] ?? [])].slice(0, MAX_TICKS) }));
    }

    if (ch?.startsWith('risk:')) {
      const sid = ch.split(':')[1];
      setRisk((prev) => ({ ...prev, [sid]: msg as unknown as RiskSummary }));
    }

    if (ch === 'risk_events') {
      const type   = (msg as Record<string, unknown>).type as string ?? 'risk_event';
      const reason = (msg as Record<string, unknown>).reason as string ?? '';
      const order  = (msg as Record<string, unknown>).order as Record<string, unknown> | undefined;
      const desc   = order
        ? `${order.strategy_id} · ${order.symbol} ${order.side} ${order.quantity} — ${reason}`
        : reason;
      pushAlert({ id: `${Date.now()}-${Math.random()}`, title: type.replace(/_/g, ' '), desc });
    }
  }, [pushAlert]);

  useWebSocket(WS_URL, handleMessage);

  const symTicks = ticks[selectedSymbol] ?? [];
  const book     = books[selectedSymbol] ?? null;

  return (
    <div className="dashboard">
      {/* Risk-event toast alerts */}
      {alerts.length > 0 && (
        <div className="alert-container" role="alert">
          {alerts.map((a) => (
            <div key={a.id} className="alert-toast">
              <span className="alert-icon">⚠️</span>
              <div className="alert-body">
                <div className="alert-title">{a.title}</div>
                <div className="alert-desc">{a.desc}</div>
              </div>
              <button type="button" className="alert-close" onClick={() => dismissAlert(a.id)}>✕</button>
            </div>
          ))}
        </div>
      )}

      {/* Header */}
      <div className="dashboard-header">
        <div className="dashboard-title-group">
          <span className="dashboard-title">🌊 AquaSim</span>
          <span className="dashboard-subtitle">Trading Simulation Platform</span>
        </div>
        <div className="dashboard-ws-indicator">
          <div className={`ws-dot ws-dot-${wsStatus}`} />
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
            className={`symbol-btn ${selectedSymbol === s ? 'symbol-btn-active' : 'symbol-btn-inactive'}`}
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
