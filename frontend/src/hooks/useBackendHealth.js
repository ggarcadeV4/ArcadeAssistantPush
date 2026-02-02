/**
 * useBackendHealth - Backend readiness check with exponential backoff retry
 *
 * Optimizes chat/API interactions by:
 * - Pre-validating backend availability before mutations
 * - Exponential backoff for transient failures
 * - UI-friendly status indicators (ready, degraded, offline)
 * - Automatic retry on recovery
 *
 * Usage:
 *   const { isReady, status, retry } = useBackendHealth()
 *   <button disabled={!isReady} onClick={sendChat}>Chat</button>
 */

import { useQuery } from '@tanstack/react-query';
import { useState, useCallback } from 'react';

export function useBackendHealth() {
  const [retryCount, setRetryCount] = useState(0);

  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ['backend-health'],
    queryFn: async () => {
      const res = await fetch('/api/health', {
        headers: {
          'x-device-id': localStorage.getItem('device_id') || 'demo_001',
        },
      });

      if (!res.ok) {
        throw new Error(`Backend responded with ${res.status}`);
      }

      return res.json();
    },
    retry: 3, // Retry failed requests
    retryDelay: (attemptIndex) => {
      // Exponential backoff: 1s, 2s, 4s
      return Math.min(1000 * Math.pow(2, attemptIndex), 10000);
    },
    refetchInterval: 30000, // Check every 30s
    staleTime: 10000, // Consider data fresh for 10s
  });

  // Determine status
  const getStatus = useCallback(() => {
    if (isLoading && retryCount === 0) return 'checking';
    if (error) return 'offline';
    if (!data) return 'unknown';

    // Check if gateway and backend are both up
    const gatewayUp = data.status === 'ok' || data.gateway?.status === 'ok';
    const backendUp = data.backend?.status === 'ok' || data.fastapi?.status === 'ok';

    if (gatewayUp && backendUp) return 'ready';
    if (gatewayUp || backendUp) return 'degraded';
    return 'offline';
  }, [data, error, isLoading, retryCount]);

  const status = getStatus();
  const isReady = status === 'ready';

  // Manual retry with backoff tracking
  const retry = useCallback(() => {
    setRetryCount((prev) => prev + 1);
    refetch();
  }, [refetch]);

  return {
    isReady,
    status, // 'checking' | 'ready' | 'degraded' | 'offline' | 'unknown'
    health: data,
    error,
    retry,
    isLoading,
  };
}

/**
 * useChat - Enhanced chat hook with backend health awareness
 *
 * Prevents chat mutations when backend is offline
 * Shows user-friendly error messages
 */
export function useChat(panel) {
  const { isReady, status, retry } = useBackendHealth();

  const sendMessage = useCallback(
    async (message, context = {}) => {
      // Block if backend not ready
      if (!isReady) {
        const errorMessages = {
          checking: 'Checking backend status...',
          degraded: 'Backend partially available - some features may not work',
          offline: 'Backend offline - please start the server',
          unknown: 'Backend status unknown - retrying...',
        };

        throw new Error(errorMessages[status] || 'Backend not ready');
      }

      // Proceed with mutation
      const res = await fetch(`/api/chat/${panel}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, context }),
      });

      if (!res.ok) {
        const error = await res.json().catch(() => ({}));
        throw new Error(error.detail || `Chat failed: ${res.status}`);
      }

      return res.json();
    },
    [isReady, status, panel]
  );

  return {
    sendMessage,
    isReady,
    status,
    retry,
  };
}
