import { getGatewayUrl, getGatewayWsUrl } from './gateway.js';
import { buildStandardHeaders, resolveDeviceId } from '../utils/identity';

function buildCorrId(prefix) {
    return `${prefix}-${Date.now()}`;
}

function buildHeaders({ panel = 'global', scope = 'state', corrId, json = true } = {}) {
    const headers = buildStandardHeaders({
        panel,
        scope,
        extraHeaders: {
            'x-corr-id': corrId || buildCorrId(panel),
        },
    });

    if (json) {
        headers['Content-Type'] = 'application/json';
    }

    return headers;
}

export const supabase = null;

export const logChatHistory = async (params = {}) => {
    const panel = params.panel || params.panel_id || 'global';
    const corrId = buildCorrId(`${panel}-chat`);

    const payload = {
        event: 'chat_history',
        ...params,
        panel,
        corr_id: corrId,
    };

    try {
        const response = await fetch(`${getGatewayUrl()}/api/frontend/log`, {
            method: 'POST',
            headers: buildHeaders({ panel, scope: 'state', corrId }),
            body: JSON.stringify(payload),
        });

        if (!response.ok) {
            console.warn('[Gateway Log] Failed to record chat history:', response.status);
        }
    } catch (err) {
        console.error('[Gateway Log] Chat history logging error:', err);
    }
};

export const subscribeToScores = (onInsert) => {
    if (typeof WebSocket === 'undefined') {
        console.warn('[Scorekeeper WS] WebSocket unavailable - skipping score subscription');
        return null;
    }

    const corrId = buildCorrId('scorekeeper');
    const params = new URLSearchParams({
        device: resolveDeviceId(),
        panel: 'scorekeeper',
        corr_id: corrId,
    });
    const url = getGatewayWsUrl(`/scorekeeper/ws?${params.toString()}`);

    let socket = null;
    let reconnectTimer = null;
    let closedByClient = false;

    const connect = () => {
        if (closedByClient) return;

        socket = new WebSocket(url);

        socket.onopen = () => {
            socket.send(JSON.stringify({ type: 'subscribe' }));
        };

        socket.onmessage = (event) => {
            try {
                const payload = JSON.parse(event.data);
                if (payload?.type === 'score_updated' && typeof onInsert === 'function') {
                    onInsert(payload.entry ?? payload.new ?? payload);
                }
            } catch (err) {
                console.warn('[Scorekeeper WS] Ignoring malformed event:', err);
            }
        };

        socket.onclose = () => {
            socket = null;
            if (!closedByClient) {
                reconnectTimer = setTimeout(connect, 1000);
            }
        };

        socket.onerror = (err) => {
            console.warn('[Scorekeeper WS] Subscription error:', err);
        };
    };

    connect();

    return {
        unsubscribe() {
            closedByClient = true;
            if (reconnectTimer) {
                clearTimeout(reconnectTimer);
                reconnectTimer = null;
            }
            if (socket && socket.readyState <= WebSocket.OPEN) {
                socket.close(1000, 'unsubscribe');
            }
        },
    };
};
