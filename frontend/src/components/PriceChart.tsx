import React from 'react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';
import { Tick } from '../types';

interface Props {
  ticks: Tick[];
  symbol: string;
}

export const PriceChart: React.FC<Props> = ({ ticks, symbol }) => {
  const data = ticks.map((t) => ({
    time: new Date(t.timestamp).toLocaleTimeString(),
    price: t.price,
    bid: t.bid,
    ask: t.ask,
  }));

  const latest = ticks[0];

  return (
    <div className="card" style={{ height: 260 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ fontWeight: 600 }}>{symbol} — Live Price</span>
        {latest && (
          <span className="mono" style={{ fontSize: 15, fontWeight: 700, color: 'var(--color-blue)' }}>
            ${latest.price.toFixed(4)}
          </span>
        )}
      </div>
      <ResponsiveContainer width="100%" height="88%">
        <LineChart data={[...data].reverse()}>
          <XAxis dataKey="time" tick={{ fill: '#8b949e', fontSize: 10 }} interval="preserveStartEnd" />
          <YAxis
            domain={['auto', 'auto']}
            tick={{ fill: '#8b949e', fontSize: 10 }}
            tickFormatter={(v) => `$${v.toFixed(2)}`}
            width={70}
          />
          <Tooltip
            contentStyle={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 6 }}
            labelStyle={{ color: '#8b949e' }}
            itemStyle={{ color: '#e6edf3' }}
          />
          <Line type="monotone" dataKey="price" stroke="#58a6ff" dot={false} strokeWidth={1.5} />
          <Line type="monotone" dataKey="bid" stroke="#3fb950" dot={false} strokeWidth={1} strokeDasharray="3 3" />
          <Line type="monotone" dataKey="ask" stroke="#f85149" dot={false} strokeWidth={1} strokeDasharray="3 3" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};
