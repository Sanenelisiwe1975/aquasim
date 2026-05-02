import React from 'react';
import { RiskSummary } from '../types';

interface Props {
  risk: RiskSummary | null;
  strategyId: string;
}

const Stat: React.FC<{ label: string; value: string; color?: string }> = ({ label, value, color }) => (
  <div style={{ padding: '8px 12px', background: '#0d1117', borderRadius: 6 }}>
    <div style={{ color: 'var(--color-muted)', fontSize: 10, marginBottom: 2 }}>{label}</div>
    <div className="mono" style={{ fontWeight: 600, color: color ?? 'var(--color-text)' }}>{value}</div>
  </div>
);

export const RiskMetrics: React.FC<Props> = ({ risk, strategyId }) => {
  if (!risk) {
    return (
      <div className="card">
        <div style={{ fontWeight: 600, marginBottom: 8 }}>{strategyId} — Risk</div>
        <span style={{ color: 'var(--color-muted)' }}>No risk data yet</span>
      </div>
    );
  }

  const ddColor = risk.drawdown_pct > risk.max_drawdown_pct * 0.8
    ? 'var(--color-red)'
    : risk.drawdown_pct > risk.max_drawdown_pct * 0.5
    ? 'var(--color-yellow)'
    : 'var(--color-green)';

  return (
    <div className="card">
      <div style={{ fontWeight: 600, marginBottom: 10 }}>{strategyId} — Risk Monitor</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }}>
        <Stat label="Equity" value={`$${risk.equity.toLocaleString()}`} />
        <Stat
          label="Daily PnL"
          value={`${risk.daily_pnl >= 0 ? '+' : ''}$${risk.daily_pnl.toFixed(0)}`}
          color={risk.daily_pnl >= 0 ? 'var(--color-green)' : 'var(--color-red)'}
        />
        <Stat
          label="Drawdown"
          value={`${risk.drawdown_pct.toFixed(2)}% / ${risk.max_drawdown_pct}%`}
          color={ddColor}
        />
        <Stat label="Peak Equity" value={`$${risk.peak_equity.toLocaleString()}`} />
      </div>
      {/* Drawdown progress bar */}
      <div style={{ marginTop: 10 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--color-muted)', marginBottom: 3 }}>
          <span>Drawdown utilisation</span>
          <span>{((risk.drawdown_pct / risk.max_drawdown_pct) * 100).toFixed(1)}%</span>
        </div>
        <div style={{ height: 6, background: '#21262d', borderRadius: 3, overflow: 'hidden' }}>
          <div
            style={{
              height: '100%',
              width: `${Math.min((risk.drawdown_pct / risk.max_drawdown_pct) * 100, 100)}%`,
              background: ddColor,
              borderRadius: 3,
              transition: 'width 0.3s ease',
            }}
          />
        </div>
      </div>
    </div>
  );
};
