import { useEffect, useRef, useState } from 'react';

const STATE_HEADERS = { 'x-scope': 'state' };
const DETECT_HEADERS = {
  'Content-Type': 'application/json',
  'x-scope': 'state',
};

export function useInputDetection(enabled = false) {
  const [latestInput, setLatestInput] = useState(null);
  const [isActive, setIsActive] = useState(false);
  const [error, setError] = useState(null);
  const mountedRef = useRef(false);
  const lastTimestampRef = useRef(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!enabled) {
      setIsActive(false);
      setLatestInput(null);
      setError(null);
      lastTimestampRef.current = null;
      return undefined;
    }

    let cancelled = false;
    let pollId = null;

    const pollLatest = () => {
      fetch('/api/local/controller/input/latest', { headers: STATE_HEADERS, cache: 'no-store' })
        .then((res) => res.json())
        .then((data) => {
          if (!mountedRef.current || cancelled) return;
          if (data?.event && data.event.timestamp !== lastTimestampRef.current) {
            lastTimestampRef.current = data.event.timestamp;
            setLatestInput(data.event);
          }
        })
        .catch(() => {});
    };

    fetch('/api/local/controller/input/start', { headers: STATE_HEADERS })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Failed to start detection (${response.status})`);
        }
        if (!cancelled && mountedRef.current) {
          setIsActive(true);
          setError(null);
          pollLatest();
          pollId = window.setInterval(pollLatest, 1000);
        }
      })
      .catch((err) => {
        if (!cancelled && mountedRef.current) {
          setIsActive(false);
          setError(err.message || 'Failed to start detection');
        }
      });

    const handleKeyDown = (event) => {
      if (!mountedRef.current) return;
      const tag = (event.target?.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea') return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;

      fetch('/api/local/controller/input/detect', {
        method: 'POST',
        headers: DETECT_HEADERS,
        body: JSON.stringify({ keycode: event.code }),
      })
        .then((res) => res.json())
        .then((data) => {
          if (!mountedRef.current) return;
          const eventData = data?.event || null;
          if (eventData) {
            lastTimestampRef.current = eventData.timestamp ?? Date.now() / 1000;
          }
          setLatestInput(eventData);
          setError(null);
        })
        .catch((err) => {
          if (mountedRef.current) {
            setError(err.message || 'Detection failed');
          }
        });
    };

    window.addEventListener('keydown', handleKeyDown);

    return () => {
      cancelled = true;
      if (pollId) {
        window.clearInterval(pollId);
      }
      window.removeEventListener('keydown', handleKeyDown);
      fetch('/api/local/controller/input/stop', { headers: STATE_HEADERS })
        .catch(() => {})
        .finally(() => {
          if (mountedRef.current) {
            setIsActive(false);
          }
        });
    };
  }, [enabled]);

  return { latestInput, isActive, error };
}
