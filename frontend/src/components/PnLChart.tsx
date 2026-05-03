import React from 'react';
import {
  Area, Line, ComposedChart,
  XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine,
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
  const hasRealized = data.some((d) => d.realized !== undefined);

  const chartData = data.map((d) => ({
    time:     new Date(d.timestamp).toLocaleTimeString(),
    total:    d.total_pnl,
    realized: d.realized,
  }));

  const strokeTotal    = isPositive ? '#3fb950' : '#f85149';
  const gradientId     = `grad-${strategyId}`;

  return (
    <div className="card h-220">
      <div className="panel-header mb-8">
        <span className="panel-title">{strategyId} — PnL</span>
        {latest && (
          <span className={`mono fw-700 ${isPositive ? 'badge-green' : 'badge-red'}`}>
            {fmt(latest.total_pnl)}
          </span>
        )}
      </div>
      <ResponsiveContainer width="100%" height="85%">
        <ComposedChart data={chartData}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor={strokeTotal} stopOpacity={0.25} />
              <stop offset="95%" stopColor={strokeTotal} stopOpacity={0}    />
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
            formatter={(v: number, name: string) => [fmt(v), name === 'total' ? 'Total PnL' : 'Realized']}
          />
          <ReferenceLine y={0} stroke="#30363d" strokeDasharray="4 4" />
          {/* Filled area for total PnL */}
          <Area
            type="monotone"
            dataKey="total"
            stroke={strokeTotal}
            fill={`url(#${gradientId})`}
            dot={false}
            strokeWidth={1.5}
            isAnimationActive={false}
          />
          {/* Dashed realized PnL line — only when data is available */}
          {hasRealized && (
            <Line
              type="monotone"
              dataKey="realized"
              stroke="#58a6ff"
              dot={false}
              strokeWidth={1}
              strokeDasharray="4 2"
              isAnimationActive={false}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
};
