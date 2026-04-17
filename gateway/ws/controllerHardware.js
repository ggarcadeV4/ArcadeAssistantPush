import { WebSocket } from 'ws';
import { buildIdentityHeaders, ensureDeviceIdentity, extractWebSocketIdentity } from './identity.js';

const WS_PATH = '/api/local/hardware/ws/encoder-events';

function buildBackendWebSocketUrl() {
  const target = process.env.FASTAPI_URL;
  if (!target) return '';

  try {
    const url = new URL(target);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    url.pathname = WS_PATH;
    url.search = '';
    url.hash = '';
    return url.toString();
  } catch {
    return '';
  }
}

function safeSend(socket, payload) {
  try {
    const openState = typeof socket.OPEN === 'number' ? socket.OPEN : WebSocket.OPEN;
    if (socket.readyState === openState) {
      socket.send(JSON.stringify(payload));
    }
  } catch (err) {
    console.error('[Controller Hardware WS] Failed to send payload:', err);
  }
}

export function setupControllerHardwareWebSocket(wss) {
  wss.on('connection', (client, req) => {
    const identity = extractWebSocketIdentity(req, {
      defaultPanel: 'controller-chuck',
      corrPrefix: 'controller-hardware'
    });
    const { url } = identity;
    if (url.pathname !== WS_PATH) {
      return;
    }

    if (!ensureDeviceIdentity(client, identity, { channel: 'controller hardware websocket' })) {
      return;
    }

    const backendTarget = process.env.CONTROLLER_HARDWARE_WS_URL || buildBackendWebSocketUrl();

    safeSend(client, {
      type: 'gateway_status',
      path: WS_PATH,
      device: identity.deviceId,
      panel: identity.panel,
      corr_id: identity.corrId,
    });

    if (!backendTarget) {
      safeSend(client, {
        type: 'gateway_notice',
        status: 'mock_mode',
        message: 'Controller hardware websocket target not configured.',
      });
      return;
    }

    const upstream = new WebSocket(backendTarget, {
      headers: buildIdentityHeaders(identity),
    });

    const closeUpstream = (code, reason) => {
      if (upstream.readyState === WebSocket.OPEN || upstream.readyState === WebSocket.CONNECTING) {
        upstream.close(code, reason);
      }
    };

    const closeClient = (code, reason) => {
      if (client.readyState === WebSocket.OPEN || client.readyState === WebSocket.CONNECTING) {
        client.close(code, reason);
      }
    };

    upstream.on('open', () => {
      safeSend(client, {
        type: 'gateway_notice',
        status: 'proxy_connected',
      });
    });

    upstream.on('message', (data, isBinary) => {
      if (client.readyState === WebSocket.OPEN) {
        client.send(data, { binary: isBinary });
      }
    });

    upstream.on('close', (code, reason) => {
      safeSend(client, {
        type: 'gateway_notice',
        status: 'proxy_closed',
        code,
        reason: reason?.toString(),
      });
      closeClient(1011, 'Controller hardware upstream closed');
    });

    upstream.on('error', (err) => {
      console.error('[Controller Hardware WS] Upstream error:', err);
      safeSend(client, {
        type: 'gateway_error',
        message: err?.message || 'Controller hardware upstream error',
      });
      closeClient(1011, 'Controller hardware upstream error');
    });

    client.on('message', (data, isBinary) => {
      if (upstream.readyState === WebSocket.OPEN) {
        upstream.send(data, { binary: isBinary });
      }
    });

    client.on('close', () => {
      closeUpstream(1000, 'client_closed');
    });

    client.on('error', (err) => {
      console.error('[Controller Hardware WS] Client error:', err);
      closeUpstream(1011, 'client_error');
    });
  });
}
