import React, { useLayoutEffect, useRef } from 'react';
import { RiskSummary } from '../types';

interface Props {
  risk: RiskSummary | null;
  strategyId: string;
}

function utilPct(value: number, limit: number): number {
  return Math.min((value / limit) * 100, 100);
}

function barColorClass(pct: number): string {
  if (pct >= 80) return 'bar-red';
  if (pct >= 50) return 'bar-yellow';
  return 'bar-green';
}

function barTextClass(pct: number): string {
  if (pct >= 80) return 'badge-red';
  if (pct >= 50) return 'badge-yellow';
  return 'badge-green';
}

interface StatProps { label: string; value: string; colorClass?: string }
const Stat: React.FC<StatProps> = ({ label, value, colorClass }) => (
  <div className="risk-stat">
    <div className="risk-stat-label">{label}</div>
    <div className={`risk-stat-value${colorClass ? ` ${colorClass}` : ''}`}>{value}</div>
  </div>
);

interface BarProps { label: string; pct: number; detail: string }
const Bar: React.FC<BarProps> = ({ label, pct, detail }) => {
  const fillRef = useRef<HTMLDivElement>(null);

  // Set CSS custom property imperatively to avoid the inline-style linter rule
  useLayoutEffect(() => {
    fillRef.current?.style.setProperty('--fill-w', `${pct}%`);
  }, [pct]);

  return (
    <div>
      <div className="risk-bar-row">
        <span>{label}</span>
        <span className={barTextClass(pct)}>{detail}</span>
      </div>
      <div className="risk-bar-track">
        <div ref={fillRef} className={`risk-bar-fill ${barColorClass(pct)}`} />
      </div>
    </div>
  );
};

export const RiskMetrics: React.FC<Props> = ({ risk, strategyId }) => {
  if (!risk) {
    return (
      <div className="card">
        <div className="panel-title mb-8">{strategyId} — Risk</div>
        <span className="badge-muted">No risk data yet</span>
      </div>
    );
  }

  const ddPct    = utilPct(risk.drawdown_pct, risk.max_drawdown_pct);
  const lossAbs  = Math.abs(Math.min(risk.daily_pnl, 0));
  const lossPct  = utilPct(lossAbs, risk.max_daily_loss_usd);
  const isBreach = ddPct >= 100 || lossPct >= 100;

  return (
    <div className={`card${isBreach ? ' risk-breach-border' : ''}`}>
      <div className="panel-title mb-10">{strategyId} — Risk Monitor</div>

      <div className="risk-stats">
        <Stat label="Equity"      value={`$${risk.equity.toLocaleString(undefined, { maximumFractionDigits: 0 })}`} />
        <Stat
          label="Daily PnL"
          value={`${risk.daily_pnl >= 0 ? '+' : ''}$${risk.daily_pnl.toFixed(0)}`}
          colorClass={risk.daily_pnl >= 0 ? 'badge-green' : 'badge-red'}
        />
        <Stat
          label="Drawdown"
          value={`${risk.drawdown_pct.toFixed(2)}% / ${risk.max_drawdown_pct}%`}
          colorClass={barTextClass(ddPct)}
        />
        <Stat label="Peak Equity" value={`$${risk.peak_equity.toLocaleString(undefined, { maximumFractionDigits: 0 })}`} />
      </div>

      <div className="risk-bar-section">
        <Bar
          label="Drawdown utilisation"
          pct={ddPct}
          detail={`${ddPct.toFixed(1)}% of ${risk.max_drawdown_pct}% limit`}
        />
        <Bar
          label="Daily loss utilisation"
          pct={lossPct}
          detail={`$${lossAbs.toFixed(0)} of $${risk.max_daily_loss_usd.toLocaleString()} limit`}
        />
      </div>
    </div>
  );
};
