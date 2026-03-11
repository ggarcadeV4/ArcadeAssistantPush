/**
 * gateway.js — Centralized gateway URL resolution
 *
 * Single source of truth for backend gateway URLs (HTTP + WebSocket).
 * Every service client and panel should import from here instead of
 * hardcoding localhost:8787.
 */

const GATEWAY_PORT = 8787

/**
 * Get the HTTP base URL for the gateway.
 * In dev (Vite port 5173) → http://localhost:8787
 * In production → same origin as the frontend
 */
export function getGatewayUrl() {
    if (typeof window === 'undefined') return `http://localhost:${GATEWAY_PORT}`
    if (window.location.port === '5173') return `http://localhost:${GATEWAY_PORT}`
    return window.location.origin
}

/**
 * Get the gateway host (without protocol) for WebSocket connections.
 * In dev → localhost:8787
 * In production → window.location.host
 */
export function getGatewayHost() {
    if (typeof window === 'undefined') return `localhost:${GATEWAY_PORT}`
    if (window.location.port === '5173') return `localhost:${GATEWAY_PORT}`
    return window.location.host
}

/**
 * Get a WebSocket URL for a given path.
 * @param {string} path - WebSocket endpoint path (e.g. '/ws/audio', '/scorekeeper/ws')
 * @returns {string} Full ws:// URL
 */
export function getGatewayWsUrl(path = '') {
    const protocol = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss' : 'ws'
    return `${protocol}://${getGatewayHost()}${path}`
}
