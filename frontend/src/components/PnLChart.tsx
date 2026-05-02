import React from 'react';
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';
import { EquityPoint } from '../types';

interface Props {
  strategyId: string;
  data: EquityPoint[];
}

const fmt = (v: number) =>
  v >= 0 ? `+$${v.toFixed(2)}` : `-$${Math.abs(v).toFixed(2)}`;

export const PnLChart: React.FC<Props> = ({ strategyId, data }) => {
  const latest = data[data.length - 1];
  const isPositive = (latest?.total_pnl ?? 0) >= 0;

  const chartData = data.map((d) => ({
    time: new Date(d.timestamp).toLocaleTimeString(),
    pnl: d.total_pnl,
  }));

  return (
    <div className="card" style={{ height: 220 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ fontWeight: 600 }}>{strategyId} — PnL</span>
        {latest && (
          <span
            className="mono"
            style={{ fontWeight: 700, color: isPositive ? 'var(--color-green)' : 'var(--color-red)' }}
          >
            {fmt(latest.total_pnl)}
          </span>
        )}
      </div>
      <ResponsiveContainer width="100%" height="85%">
        <AreaChart data={chartData}>
          <defs>
            <linearGradient id={`grad-${strategyId}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={isPositive ? '#3fb950' : '#f85149'} stopOpacity={0.3} />
              <stop offset="95%" stopColor={isPositive ? '#3fb950' : '#f85149'} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="time" tick={{ fill: '#8b949e', fontSize: 10 }} interval="preserveStartEnd" />
          <YAxis
            tick={{ fill: '#8b949e', fontSize: 10 }}
            tickFormatter={fmt}
            width={80}
          />
          <Tooltip
            contentStyle={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 6 }}
            formatter={(v: number) => [fmt(v), 'PnL']}
          />
          <ReferenceLine y={0} stroke="#30363d" strokeDasharray="4 4" />
          <Area
            type="monotone"
            dataKey="pnl"
            stroke={isPositive ? '#3fb950' : '#f85149'}
            fill={`url(#grad-${strategyId})`}
            dot={false}
            strokeWidth={1.5}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
};
