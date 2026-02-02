// Frontend Hotkey WebSocket client (singleton)
// Connects via gateway to backend hotkey stream and notifies listeners

class HotkeyWebSocketClient {
  constructor() {
    this.ws = null
    this.listeners = new Set()
    this._reconnectTimer = null
    const isSecure = typeof window !== 'undefined' && window.location.protocol === 'https:'
    const host = typeof window !== 'undefined' ? window.location.host : 'localhost:8787'
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
      console.error('[Hotkey WS] Failed to create WebSocket:', err)
      this._scheduleReconnect()
      return
    }

    this.ws.onopen = () => {
      // console.log('[Hotkey WS] Connected')
      this._notify({ type: 'connected' })
    }
    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        this._notify(data)
      } catch (e) {
        console.error('[Hotkey WS] Message parse error:', e)
      }
    }
    this.ws.onerror = (e) => {
      console.error('[Hotkey WS] Error:', e)
      this._notify({ type: 'error', message: 'hotkey_ws_error' })
    }
    this.ws.onclose = () => {
      // console.log('[Hotkey WS] Disconnected')
      this._notify({ type: 'disconnected' })
      this._scheduleReconnect()
    }
  }

  _scheduleReconnect() {
    if (this._reconnectTimer) return
    this._reconnectTimer = setTimeout(() => {
      this._reconnectTimer = null
      this.connect()
    }, 2000)
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
