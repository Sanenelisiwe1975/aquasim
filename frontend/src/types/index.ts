export interface Tick {
  symbol: string;
  price: number;
  bid: number;
  ask: number;
  bid_size: number;
  ask_size: number;
  volume: number;
  timestamp: string;
  sequence: number;
}

export interface OrderBookLevel {
  price: number;
  size: number;
}

export interface OrderBook {
  symbol: string;
  sequence: number;
  timestamp: string;
  last_trade_price: number;
  bids: [number, number][];
  asks: [number, number][];
  mid: number | null;
  spread: number | null;
}

export interface Position {
  strategy_id: string;
  symbol: string;
  quantity: number;
  avg_entry_price: number;
  last_price: number;
  realized_pnl: number;
  unrealized_pnl: number;
  total_pnl: number;
  notional: number;
  last_updated: string;
}

export interface Trade {
  id: string;
  order_id: string;
  strategy_id: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  quantity: number;
  price: number;
  notional: number;
  latency_us: number;
  slippage: number;
  realized_pnl: number;
  timestamp: string;
  _channel?: string;
}

export interface RiskSummary {
  strategy_id: string;
  equity: number;
  peak_equity: number;
  drawdown_pct: number;
  daily_pnl: number;
  max_position_usd: number;
  max_drawdown_pct: number;
  max_daily_loss_usd: number;
}

export interface EquityPoint {
  timestamp: string;
  total_pnl: number;
}

export interface WsMessage {
  _channel: string;
  [key: string]: unknown;
}
