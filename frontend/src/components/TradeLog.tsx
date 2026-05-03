import React, { useState, useMemo } from 'react';
import { Trade } from '../types';

interface Props {
  trades: Trade[];
}

export const TradeLog: React.FC<Props> = ({ trades }) => {
  const [symFilter, setSymFilter]   = useState('');
  const [stratFilter, setStratFilter] = useState('');

  const filtered = useMemo(() =>
    trades.filter((t) => {
      if (symFilter   && !t.symbol.toLowerCase().includes(symFilter.toLowerCase()))      return false;
      if (stratFilter && !t.strategy_id.toLowerCase().includes(stratFilter.toLowerCase())) return false;
      return true;
    }),
    [trades, symFilter, stratFilter]
  );

  return (
    <div className="card scrollable max-h-280">
      <div className="panel-header">
        <span className="panel-title">Recent Trades</span>
        <div className="filter-row">
          <input className="filter-input" placeholder="Symbol…"   value={symFilter}   onChange={(e) => setSymFilter(e.target.value)} />
          <input className="filter-input" placeholder="Strategy…" value={stratFilter} onChange={(e) => setStratFilter(e.target.value)} />
        </div>
      </div>

      {filtered.length === 0 ? (
        <span className="badge-muted">
          {trades.length === 0 ? 'No trades yet…' : 'No trades match filter'}
        </span>
      ) : (
        <table className="trade-table">
          <thead className="sticky-thead">
            <tr>
              {['Time', 'Strategy', 'Symbol', 'Side', 'Qty', 'Price', 'Latency', 'Slippage'].map((h) => (
                <th key={h}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((t) => (
              <tr key={t.id} className="data-row">
                <td className="mono badge-muted">{new Date(t.timestamp).toLocaleTimeString()}</td>
                <td className="badge-blue text-xs">{t.strategy_id}</td>
                <td className="mono fw-600">{t.symbol}</td>
                <td className={`text-right fw-600 ${t.side === 'BUY' ? 'badge-green' : 'badge-red'}`}>{t.side}</td>
                <td className="mono text-right">{t.quantity}</td>
                <td className="mono text-right">${t.price.toFixed(4)}</td>
                <td className="mono text-right badge-yellow">{t.latency_us}µs</td>
                <td className="mono text-right badge-muted">{t.slippage.toFixed(6)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};
