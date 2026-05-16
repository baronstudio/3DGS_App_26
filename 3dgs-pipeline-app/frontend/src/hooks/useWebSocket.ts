import { useState, useEffect, useRef } from 'react';
import { usePipelineStore } from '../store/pipelineStore';
import type { WsMessage } from '../types';

const WS_URL = 'ws://localhost:8000/ws/logs';
const MAX_RETRIES = 5;

export const useWebSocket = () => {
  const [connected, setConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WsMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Tracks whether the hook is intentionally mounted — prevents StrictMode's
  // cleanup→remount cycle from spawning a second connection via auto-reconnect.
  const mountedRef = useRef(false);

  const connect = () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      retriesRef.current = 0;
    };

    ws.onmessage = (event: MessageEvent) => {
      try {
        const msg = JSON.parse(event.data as string) as WsMessage;
        setLastMessage(msg);
        usePipelineStore.getState().handleWsMessage(msg);
      } catch {
        // malformed message — ignore
      }
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;

      // Only auto-reconnect if the component is still intentionally mounted
      // (avoids a spurious second connection when React StrictMode unmounts
      // and immediately remounts the component during development).
      if (mountedRef.current && retriesRef.current < MAX_RETRIES) {
        const delay = Math.min(1000 * 2 ** retriesRef.current, 30_000);
        retriesRef.current += 1;
        timeoutRef.current = setTimeout(connect, delay);
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  };

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      wsRef.current?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { connected, lastMessage };
};

export default useWebSocket;
