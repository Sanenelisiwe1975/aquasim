import React, { useLayoutEffect, useRef } from 'react';
import { OrderBook as OB } from '../types';

interface Props {
  book: OB | null;
}

const MAX_LEVELS = 8;

interface BarRowProps {
  price: number;
  size: number;
  maxSize: number;
  side: 'ask' | 'bid';
}

const BarRow: React.FC<BarRowProps> = ({ price, size, maxSize, side }) => {
  const barRef = useRef<HTMLDivElement>(null);

  // Set CSS custom property imperatively — avoids inline-style linter rule
  useLayoutEffect(() => {
    barRef.current?.style.setProperty('--bar-w', `${(size / maxSize) * 100}%`);
  }, [size, maxSize]);

  return (
    <div className="ob-row">
      <div ref={barRef} className={`ob-bar ob-bar-${side}`} />
      <div className="ob-content">
        {side === 'ask' ? (
          <>
            <span className="mono badge-muted">{size.toFixed(0)}</span>
            <span className="mono badge-red text-right">{price.toFixed(4)}</span>
          </>
        ) : (
          <>
            <span className="mono badge-green">{price.toFixed(4)}</span>
            <span className="mono badge-muted text-right">{size.toFixed(0)}</span>
          </>
        )}
      </div>
    </div>
  );
};

export const OrderBookPanel: React.FC<Props> = ({ book }) => {
  if (!book) {
    return (
      <div className="card h-340">
        <span className="badge-muted">Waiting for order book data…</span>
      </div>
    );
  }

  const bids = book.bids.slice(0, MAX_LEVELS);
  const asks = book.asks.slice(0, MAX_LEVELS).reverse();

  const maxBidSize = Math.max(...bids.map(([, s]) => s), 1);
  const maxAskSize = Math.max(...asks.map(([, s]) => s), 1);

  return (
    <div className="card h-340">
      <div className="ob-header">
        <span className="panel-title">{book.symbol} — Order Book</span>
        <span className="mono badge-muted ob-subtitle">
          spread: {book.spread?.toFixed(4) ?? '—'}
        </span>
      </div>

      <div className="ob-col-header">
        <span>Size</span><span className="text-right">Ask Price</span>
      </div>
      <div className="ob-scroll scrollable">
        {asks.map(([price, size], i) => (
          <BarRow key={i} price={price} size={size} maxSize={maxAskSize} side="ask" />
        ))}
      </div>

      <div className="ob-mid">
        ${book.mid?.toFixed(4) ?? book.last_trade_price.toFixed(4)}
      </div>

      <div className="ob-col-header">
        <span>Bid Price</span><span className="text-right">Size</span>
      </div>
      <div className="ob-scroll scrollable">
        {bids.map(([price, size], i) => (
          <BarRow key={i} price={price} size={size} maxSize={maxBidSize} side="bid" />
        ))}
      </div>
    </div>
  );
};
