import React from 'react';
import { Trade } from '../types';

interface Props {
  trades: Trade[];
}

export const TradeLog: React.FC<Props> = ({ trades }) => (
  <div className="card scrollable" style={{ maxHeight: 280 }}>
    <div style={{ fontWeight: 600, marginBottom: 10 }}>Recent Trades</div>
    {trades.length === 0 ? (
      <span style={{ color: 'var(--color-muted)' }}>No trades yet…</span>
    ) : (
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
        <thead style={{ position: 'sticky', top: 0, background: 'var(--color-surface)' }}>
          <tr style={{ color: 'var(--color-muted)', borderBottom: '1px solid var(--color-border)' }}>
            {['Time', 'Strategy', 'Symbol', 'Side', 'Qty', 'Price', 'Latency', 'Slippage'].map((h) => (
              <th key={h} style={{ padding: '3px 6px', textAlign: 'right', fontWeight: 500 }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <tr key={t.id} style={{ borderBottom: '1px solid #21262d' }}>
              <td style={{ padding: '3px 6px', color: 'var(--color-muted)' }} className="mono">
                {new Date(t.timestamp).toLocaleTimeString()}
              </td>
              <td style={{ padding: '3px 6px', color: 'var(--color-blue)', fontSize: 10 }}>{t.strategy_id}</td>
              <td style={{ padding: '3px 6px', fontWeight: 600 }} className="mono">{t.symbol}</td>
              <td style={{ padding: '3px 6px', textAlign: 'right', color: t.side === 'BUY' ? 'var(--color-green)' : 'var(--color-red)', fontWeight: 700 }}>
                {t.side}
              </td>
              <td style={{ padding: '3px 6px', textAlign: 'right' }} className="mono">{t.quantity}</td>
              <td style={{ padding: '3px 6px', textAlign: 'right' }} className="mono">${t.price.toFixed(4)}</td>
              <td style={{ padding: '3px 6px', textAlign: 'right', color: 'var(--color-yellow)' }} className="mono">
                {t.latency_us}µs
              </td>
              <td style={{ padding: '3px 6px', textAlign: 'right', color: 'var(--color-muted)' }} className="mono">
                {t.slippage.toFixed(6)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    )}
  </div>
);
