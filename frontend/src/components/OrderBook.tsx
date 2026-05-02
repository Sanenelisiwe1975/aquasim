import React from 'react';
import { OrderBook as OB } from '../types';

interface Props {
  book: OB | null;
}

const MAX_LEVELS = 8;

export const OrderBookPanel: React.FC<Props> = ({ book }) => {
  if (!book) {
    return (
      <div className="card" style={{ height: 340 }}>
        <span style={{ color: 'var(--color-muted)' }}>Waiting for order book data…</span>
      </div>
    );
  }

  const bids = book.bids.slice(0, MAX_LEVELS);
  const asks = book.asks.slice(0, MAX_LEVELS).reverse();

  const maxBidSize = Math.max(...bids.map(([, s]) => s), 1);
  const maxAskSize = Math.max(...asks.map(([, s]) => s), 1);

  return (
    <div className="card" style={{ height: 340 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ fontWeight: 600 }}>{book.symbol} — Order Book</span>
        <span className="mono badge-muted" style={{ fontSize: 11 }}>
          spread: {book.spread?.toFixed(4) ?? '—'}
        </span>
      </div>

      {/* Header */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, fontSize: 10, color: 'var(--color-muted)', marginBottom: 4 }}>
        <span>Size</span><span style={{ textAlign: 'right' }}>Ask Price</span>
      </div>

      {/* Asks (reversed — lowest ask at bottom) */}
      <div className="scrollable" style={{ maxHeight: 110 }}>
        {asks.map(([price, size], i) => (
          <div key={i} style={{ position: 'relative', marginBottom: 1 }}>
            <div
              style={{
                position: 'absolute', right: 0, top: 0, bottom: 0,
                width: `${(size / maxAskSize) * 100}%`,
                background: 'rgba(248,81,73,0.15)',
              }}
            />
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', position: 'relative', padding: '1px 4px' }}>
              <span className="mono badge-muted">{size.toFixed(0)}</span>
              <span className="mono badge-red" style={{ textAlign: 'right' }}>{price.toFixed(4)}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Mid price */}
      <div style={{ textAlign: 'center', padding: '6px 0', fontWeight: 700, color: 'var(--color-blue)', fontFamily: 'JetBrains Mono' }}>
        ${book.mid?.toFixed(4) ?? book.last_trade_price.toFixed(4)}
      </div>

      {/* Bids */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, fontSize: 10, color: 'var(--color-muted)', marginBottom: 4 }}>
        <span>Bid Price</span><span style={{ textAlign: 'right' }}>Size</span>
      </div>
      <div className="scrollable" style={{ maxHeight: 110 }}>
        {bids.map(([price, size], i) => (
          <div key={i} style={{ position: 'relative', marginBottom: 1 }}>
            <div
              style={{
                position: 'absolute', left: 0, top: 0, bottom: 0,
                width: `${(size / maxBidSize) * 100}%`,
                background: 'rgba(63,185,80,0.15)',
              }}
            />
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', position: 'relative', padding: '1px 4px' }}>
              <span className="mono badge-green">{price.toFixed(4)}</span>
              <span className="mono badge-muted" style={{ textAlign: 'right' }}>{size.toFixed(0)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
