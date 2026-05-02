import { useEffect, useRef, useCallback } from 'react';

type MessageHandler = (data: unknown) => void;

export function useWebSocket(url: string, onMessage: MessageHandler) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();

  const connect = useCallback(() => {
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[WS] connected', url);
      // Heartbeat
      const ping = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send('ping');
      }, 20_000);
      ws.onclose = () => {
        clearInterval(ping);
        console.log('[WS] disconnected — reconnecting in 2s');
        reconnectTimer.current = setTimeout(connect, 2_000);
      };
    };

    ws.onmessage = (evt) => {
      try {
        onMessage(JSON.parse(evt.data));
      } catch {
        // ignore malformed messages
      }
    };

    ws.onerror = () => ws.close();
  }, [url, onMessage]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);
}
