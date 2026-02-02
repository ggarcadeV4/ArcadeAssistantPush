import { useEffect, useRef, useState } from 'react';

export function useControllerEvents(enabled = true) {
  const [latestEvent, setLatestEvent] = useState(null);
  const [events, setEvents] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const eventSourceRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);

  useEffect(() => {
    let cancelled = false;

    const cleanup = () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };

    const connect = () => {
      if (!enabled || cancelled) return;
      cleanup();

      const source = new EventSource('/api/controller/ai/events');
      eventSourceRef.current = source;

      source.onopen = () => setIsConnected(true);

      source.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setLatestEvent(data);
          setEvents((prev) => [...prev.slice(-49), data]);
        } catch (err) {
          console.warn('[ControllerEvents] Failed to parse event payload', err);
        }
      };

      source.onerror = () => {
        setIsConnected(false);
        cleanup();
        if (!cancelled) {
          reconnectTimeoutRef.current = setTimeout(connect, 3000);
        }
      };
    };

    if (enabled) {
      connect();
    } else {
      cleanup();
    }

    return () => {
      cancelled = true;
      cleanup();
    };
  }, [enabled]);

  return {
    latestEvent,
    events,
    isConnected,
  };
}
