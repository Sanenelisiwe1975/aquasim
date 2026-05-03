import React, { useState, useMemo } from 'react';
import { Position } from '../types';

interface Props {
  positions: Position[];
}

type SortKey = 'strategy_id' | 'symbol' | 'quantity' | 'avg_entry_price'
  | 'last_price' | 'unrealized_pnl' | 'realized_pnl' | 'total_pnl';

const COLS: { key: SortKey; label: string; left?: boolean }[] = [
  { key: 'strategy_id',     label: 'Strategy',   left: true },
  { key: 'symbol',          label: 'Symbol',     left: true },
  { key: 'quantity',        label: 'Qty' },
  { key: 'avg_entry_price', label: 'Avg Entry' },
  { key: 'last_price',      label: 'Last' },
  { key: 'unrealized_pnl',  label: 'Unreal PnL' },
  { key: 'realized_pnl',    label: 'Real PnL' },
  { key: 'total_pnl',       label: 'Total PnL' },
];

function pnlClass(v: number) { return v >= 0 ? 'badge-green' : 'badge-red'; }

export const PositionsTable: React.FC<Props> = ({ positions }) => {
  const [sortKey, setSortKey] = useState<SortKey>('total_pnl');
  const [sortAsc, setSortAsc] = useState(false);
  const [symFilter, setSymFilter] = useState('');
  const [stratFilter, setStratFilter] = useState('');

  const sorted = useMemo(() => {
    let rows = positions.filter((p) => {
      if (symFilter   && !p.symbol.toLowerCase().includes(symFilter.toLowerCase()))      return false;
      if (stratFilter && !p.strategy_id.toLowerCase().includes(stratFilter.toLowerCase())) return false;
      return true;
    });
    return [...rows].sort((a, b) => {
      const av = a[sortKey] as number | string;
      const bv = b[sortKey] as number | string;
      if (typeof av === 'string') return sortAsc ? av.localeCompare(bv as string) : (bv as string).localeCompare(av);
      return sortAsc ? (av as number) - (bv as number) : (bv as number) - (av as number);
    });
  }, [positions, sortKey, sortAsc, symFilter, stratFilter]);

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) setSortAsc((v) => !v);
    else { setSortKey(key); setSortAsc(false); }
  };

  const sortIcon = (key: SortKey) => key !== sortKey ? '' : sortAsc ? ' ↑' : ' ↓';

  return (
    <div className="card">
      <div className="panel-header">
        <span className="panel-title">Open Positions</span>
        <div className="filter-row">
          <input className="filter-input" placeholder="Symbol…"   value={symFilter}   onChange={(e) => setSymFilter(e.target.value)} />
          <input className="filter-input" placeholder="Strategy…" value={stratFilter} onChange={(e) => setStratFilter(e.target.value)} />
        </div>
      </div>

      {sorted.length === 0 ? (
        <span className="badge-muted">
          {positions.length === 0 ? 'No open positions' : 'No positions match filter'}
        </span>
      ) : (
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                {COLS.map((c) => (
                  <th
                    key={c.key}
                    className={`sortable-th${c.left ? ' text-left' : ''}`}
                    onClick={() => toggleSort(c.key)}
                  >
                    {c.label}{sortIcon(c.key)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((p, i) => (
                <tr key={i} className="data-row">
                  <td className="badge-blue">{p.strategy_id}</td>
                  <td className="mono fw-600">{p.symbol}</td>
                  <td className={`mono text-right ${p.quantity > 0 ? 'badge-green' : 'badge-red'}`}>
                    {p.quantity > 0 ? '+' : ''}{p.quantity.toFixed(0)}
                  </td>
                  <td className="mono text-right">${p.avg_entry_price.toFixed(4)}</td>
                  <td className="mono text-right">${p.last_price.toFixed(4)}</td>
                  <td className={`mono text-right ${pnlClass(p.unrealized_pnl)}`}>
                    {p.unrealized_pnl >= 0 ? '+' : ''}${p.unrealized_pnl.toFixed(2)}
                  </td>
                  <td className={`mono text-right ${pnlClass(p.realized_pnl)}`}>
                    {p.realized_pnl >= 0 ? '+' : ''}${p.realized_pnl.toFixed(2)}
                  </td>
                  <td className={`mono text-right fw-600 ${pnlClass(p.total_pnl)}`}>
                    {p.total_pnl >= 0 ? '+' : ''}${p.total_pnl.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
