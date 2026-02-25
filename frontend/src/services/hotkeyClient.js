// Frontend Hotkey WebSocket client (singleton)
// Connects via gateway to backend hotkey stream and notifies listeners

class HotkeyWebSocketClient {
  constructor() {
    this.ws = null
    this.listeners = new Set()
    this._reconnectTimer = null
    this._backoff = 2000
    this._maxBackoff = 30000
    const isSecure = typeof window !== 'undefined' && window.location.protocol === 'https:'
    // Dynamic URL: use window.location.host to avoid 127.0.0.1 vs localhost mismatch
    const host = typeof window !== 'undefined'
      ? (window.location.port === '5173' ? 'localhost:8787' : window.location.host)
      : 'localhost:8787'
    const scheme = isSecure ? 'wss' : 'ws'
    this._url = `${scheme}://${host}/ws/hotkey`
  }

  connect() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return
    }
    try {
      this.ws = new WebSocket(this._url)
    } catch (err) {
      console.warn('[Hotkey WS] Connection failed, retrying...')
      this._scheduleReconnect()
      return
    }

    this.ws.onopen = () => {
      // console.log('[Hotkey WS] Connected')
      this._backoff = 2000
      this._notify({ type: 'connected' })
    }
    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        this._notify(data)
      } catch (e) {
        console.warn('[Hotkey WS] Message parse error:', e)
      }
    }
    this.ws.onerror = () => {
      // Silently handled — onclose triggers reconnect
    }
    this.ws.onclose = () => {
      this._notify({ type: 'disconnected' })
      this._scheduleReconnect()
    }
  }

  _scheduleReconnect() {
    if (this._reconnectTimer) return
    this._reconnectTimer = setTimeout(() => {
      this._reconnectTimer = null
      this.connect()
    }, this._backoff)
    this._backoff = Math.min(this._backoff * 2, this._maxBackoff)
  }

  _notify(payload) {
    this.listeners.forEach((cb) => {
      try { cb(payload) } catch (e) { console.error('[Hotkey WS] listener error:', e) }
    })
  }

  addListener(cb) { this.listeners.add(cb) }
  removeListener(cb) { this.listeners.delete(cb) }
}

export const hotkeyClient = new HotkeyWebSocketClient()
