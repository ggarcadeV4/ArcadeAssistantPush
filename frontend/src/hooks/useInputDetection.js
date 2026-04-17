import { useEffect, useRef, useState } from 'react';
import { buildStandardHeaders } from '../utils/identity';

const STATE_HEADERS = buildStandardHeaders({ panel: 'input-detection', scope: 'state' });
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

    fetch('/api/local/controller/input/start?learn_mode=true', { method: 'GET', headers: STATE_HEADERS })
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

    return () => {
      cancelled = true;
      if (pollId) {
        window.clearInterval(pollId);
      }
      fetch('/api/local/controller/input/stop', { method: 'GET', headers: STATE_HEADERS })
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
