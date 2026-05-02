import React from 'react';
import { Position } from '../types';

interface Props {
  positions: Position[];
}

export const PositionsTable: React.FC<Props> = ({ positions }) => (
  <div className="card">
    <div style={{ fontWeight: 600, marginBottom: 10 }}>Open Positions</div>
    {positions.length === 0 ? (
      <span style={{ color: 'var(--color-muted)' }}>No open positions</span>
    ) : (
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ color: 'var(--color-muted)', borderBottom: '1px solid var(--color-border)' }}>
              {['Strategy', 'Symbol', 'Qty', 'Avg Entry', 'Last', 'Unreal PnL', 'Real PnL', 'Total PnL'].map((h) => (
                <th key={h} style={{ padding: '4px 8px', textAlign: 'right', fontWeight: 500 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {positions.map((p, i) => {
              const isLong = p.quantity > 0;
              return (
                <tr key={i} style={{ borderBottom: '1px solid #21262d' }}>
                  <td style={{ padding: '5px 8px', color: 'var(--color-blue)' }}>{p.strategy_id}</td>
                  <td style={{ padding: '5px 8px', fontWeight: 600 }} className="mono">{p.symbol}</td>
                  <td style={{ padding: '5px 8px', textAlign: 'right', color: isLong ? 'var(--color-green)' : 'var(--color-red)' }} className="mono">
                    {isLong ? '+' : ''}{p.quantity.toFixed(0)}
                  </td>
                  <td style={{ padding: '5px 8px', textAlign: 'right' }} className="mono">${p.avg_entry_price.toFixed(4)}</td>
                  <td style={{ padding: '5px 8px', textAlign: 'right' }} className="mono">${p.last_price.toFixed(4)}</td>
                  <td style={{ padding: '5px 8px', textAlign: 'right', color: p.unrealized_pnl >= 0 ? 'var(--color-green)' : 'var(--color-red)' }} className="mono">
                    {p.unrealized_pnl >= 0 ? '+' : ''}${p.unrealized_pnl.toFixed(2)}
                  </td>
                  <td style={{ padding: '5px 8px', textAlign: 'right', color: p.realized_pnl >= 0 ? 'var(--color-green)' : 'var(--color-red)' }} className="mono">
                    {p.realized_pnl >= 0 ? '+' : ''}${p.realized_pnl.toFixed(2)}
                  </td>
                  <td style={{ padding: '5px 8px', textAlign: 'right', fontWeight: 600, color: p.total_pnl >= 0 ? 'var(--color-green)' : 'var(--color-red)' }} className="mono">
                    {p.total_pnl >= 0 ? '+' : ''}${p.total_pnl.toFixed(2)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    )}
  </div>
);
